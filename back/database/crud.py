from sqlalchemy import and_, or_, desc, exists, case, literal, func
from sqlalchemy.orm import (
    Session,
    joinedload,
    selectinload,
    subqueryload,
    with_expression,
)
from sqlalchemy.sql import alias, select, column
from database.models import *
from database.schemas import *


async def create_user(db: Session, user: HashedUser):
    user = Users(**user.model_dump())
    db.add(user)
    db.commit()
    return user


async def create_user_external_map(db: Session, user_external_map: UserExternalMap):
    user_external_map = UserExternalMapping(**user_external_map.model_dump())
    db.add(user_external_map)
    db.commit()
    return user_external_map


async def create_post(db: Session, post: PostForm, author_id: str, temp_post_id: int):
    post = Posts(**post.model_dump(), author_id=author_id)
    db.add(post)
    db.flush()

    temp_post = db.query(TempPosts).filter(TempPosts.author_id == author_id).first()
    for image in temp_post.images:
        image.temp_post_id = None
        image.post_id = post.post_id
        db.commit()

    db.delete(temp_post)
    db.commit()
    return post


async def create_temp_post(db: Session, author_id: str):
    temp_post = db.query(TempPosts).filter(TempPosts.author_id == author_id).first()
    if temp_post:
        db.delete(temp_post)
        db.flush()

    temp_post = TempPosts(author_id=author_id)
    db.add(temp_post)
    db.commit()
    return temp_post


async def create_comment(db: Session, comment: CommentForm, user_id: str):
    comment = Comments(**comment.model_dump(), author_id=user_id)
    db.add(comment)
    db.flush()
    comment.post.increment_comment_count()
    if comment.parent_comment:
        comment.parent_comment.increment_child_comment_count()

        notification = Notifications(
            receiver_id=comment.parent_comment.author_id,
            reference_id=comment.post.post_id,
            content="대댓글달림"
        )
        db.add(notification)

    notification = Notifications(
        receiver_id=comment.post.author_id,
        reference_id=comment.post.post_id,
        category=comment.post.category,
        content="댓글달림",
    )
    db.add(notification)

    db.commit()
    return comment


async def create_post_scrap(db: Session, user_id: str, post_id: int):
    user = db.query(Users).filter(Users.user_id == user_id).first()
    post = db.query(Posts).filter(Posts.post_id == post_id).first()
    user.scrapped_posts.append(post)
    post.increment_scrap_count()

    notification = Notifications(
        receiver_id=post.author_id,
        reference_id=post.post_id,
        category=post.category,
        content="스크랩됨",
    )
    db.add(notification)

    db.commit()


async def create_post_like(db: Session, user_id: str, post_id: int):
    user = db.query(Users).filter(Users.user_id == user_id).first()
    post = db.query(Posts).filter(Posts.post_id == post_id).first()
    user.liked_posts.append(post)
    post.increment_like_count()

    notification = Notifications(
        receiver_id=post.author_id,
        reference_id=post.post_id,
        category=post.category,
        content="좋아요눌림",
    )
    db.add(notification)

    db.commit()


async def create_comment_like(db: Session, user_id: str, comment_id: int):
    user = db.query(Users).filter(Users.user_id == user_id).first()
    comment = db.query(Comments).filter(Comments.comment_id == comment_id).first()
    user.liked_comments.append(comment)
    comment.increment_like_count()

    notification = Notifications(
        receiver_id=comment.author_id,
        reference_id=comment.post.post_id,
        category=comment.post.category,
        content="댓글 좋아요 눌림",
    )
    db.add(notification)

    db.commit()


async def create_follow(db: Session, follower_user_id: str, followee_user_id: str):
    follow = Follows(
        follower_user_id=follower_user_id, followee_user_id=followee_user_id
    )
    db.add(follow)

    notification = Notifications(
        receiver_id=followee_user_id,
        content="팔로우됨",
    )
    db.add(notification)

    db.commit()
    return follow


async def read_user_by_id(db: Session, user_id: str, signed_in_user_id: str = None):
    query = db.query(Users)
    if signed_in_user_id:
        query = query.outerjoin(
            Follows,
            and_(Follows.follower_user_id == signed_in_user_id, Follows.followee_user_id == user_id),
        )
        query = query.options(
            with_expression(
                Users.followed,
                case((Follows.follower_user_id.isnot(None), True), else_=False).label("followed"),
            )
        )
    else:
        query = query.options(
            with_expression(Users.followed, literal(False).label("followed")),
        )

    return query.filter(Users.user_id == user_id).first()


async def read_user_by_email(db: Session, email: str):
    return db.query(Users).filter(Users.email == email).first()


async def read_user_external_map(db: Session, external_id: str, provider: str):
    return (
        db.query(UserExternalMapping)
        .filter(
            and_(
                UserExternalMapping.external_id == external_id,
                UserExternalMapping.provider == provider,
            )
        )
        .first()
    )


async def read_post(db: Session, post_id: int):
    return db.query(Posts).filter(Posts.post_id == post_id).first()


async def read_post_with_view(db: Session, post_id: int, user_id: str | None):
    query = db.query(Posts)

    if user_id:
        query = query.outerjoin(
            PostScraps,
            and_(Posts.post_id == PostScraps.post_id, PostScraps.user_id == user_id),
        ).outerjoin(
            PostLikes,
            and_(Posts.post_id == PostLikes.post_id, PostLikes.user_id == user_id),
        )
        query = query.options(
            with_expression(
                Posts.scrapped,
                case((PostScraps.user_id.isnot(None), True), else_=False).label(
                    "scrapped"
                ),
            ),
            with_expression(
                Posts.liked,
                case((PostLikes.user_id.isnot(None), True), else_=False).label("liked"),
            ),
        )
    else:
        query = query.options(
            with_expression(Posts.scrapped, literal(False).label("scrapped")),
            with_expression(Posts.liked, literal(False).label("liked")),
        )

    post = (
        query.filter(Posts.post_id == post_id)
        .options(joinedload(Posts.author), joinedload(Posts.images))
        .first()
    )

    if post:
        post.increment_view_count()
        post = Post.model_validate(post)
        db.commit()
    return post


async def read_comment(db: Session, comment_id: int):
    return db.query(Comments).filter(Comments.comment_id == comment_id).first()


async def read_comments(db: Session, post_id: int):
    comments = (
        db.query(Comments)
        .options(
            selectinload(Comments.child_comments).selectinload(Comments.author),
            selectinload(Comments.author),
        )
        .filter(Comments.post_id == post_id, Comments.parent_comment_id.is_(None))
        .all()
    )

    return comments


async def read_follow(db: Session, follower_user_id: str, followee_user_id: str):
    return (
        db.query(Follows)
        .filter(
            and_(
                Follows.follower_user_id == follower_user_id,
                Follows.followee_user_id == followee_user_id,
            )
        )
        .first()
    )


async def search_posts(
    db: Session,
    category: str | None = None,
    author_id: str | None = None,
    keyword: str | None = None,
    order: str = "newest",
    per: int = 24,
    page: int = 1,
    user_id: str | None = None,
    scrapped: bool = False,
):
    query = db.query(Posts)

    if user_id:
        if scrapped:
            query = query.join(
                PostScraps,
                and_(
                    Posts.post_id == PostScraps.post_id, PostScraps.user_id == user_id
                ),
            )
        else:
            query = query.outerjoin(
                PostScraps,
                and_(
                    Posts.post_id == PostScraps.post_id, PostScraps.user_id == user_id
                ),
            )

        query = query.outerjoin(
            PostLikes,
            and_(Posts.post_id == PostLikes.post_id, PostLikes.user_id == user_id),
        )

        query = query.options(
            with_expression(
                Posts.scrapped,
                case((PostScraps.user_id.isnot(None), True), else_=False).label(
                    "scrapped"
                ),
            ),
            with_expression(
                Posts.liked,
                case((PostLikes.user_id.isnot(None), True), else_=False).label("liked"),
            ),
        )
    else:
        query = query.options(
            with_expression(Posts.scrapped, literal(False).label("scrapped")),
            with_expression(Posts.liked, literal(False).label("liked")),
        )

    if category:
        query = query.filter(Posts.category == category)

    if author_id:
        query = query.filter(Posts.author_id == author_id)

    if keyword:
        query = query.filter(
            or_(
                Posts.title.ilike(f"%{keyword}%"),
                Posts.content.ilike(f"%{keyword}%"),
            )
        )

    if order == "newest":
        query = query.order_by(desc(Posts.created_at))
    elif order == "most_viewed":
        query = query.order_by(desc(Posts.view_count))
    elif order == "most_scrapped":
        query = query.order_by(desc(Posts.scrap_count))
    elif order == "most_liked":
        query = query.order_by(desc(Posts.like_count))

    query = query.options(joinedload(Posts.author), subqueryload(Posts.images))
    offset = per * (page - 1)
    query = query.limit(per).offset(offset)

    return query.all()


async def search_comment(db: Session, author_id: str = None, post_id: int = None):
    query = db.query(Comments)

    if post_id:
        query = query.filter(Comments.post_id == post_id)

    if author_id:
        query = query.filter(Comments.author_id == author_id)

    return query.all()


async def read_post_scrap(db: Session, user_id: str, post_id: int):
    return (
        db.query(PostScraps)
        .filter(PostScraps.user_id == user_id, PostScraps.post_id == post_id)
        .first()
    )


async def read_post_like(db: Session, user_id: str, post_id: int):
    return (
        db.query(PostLikes)
        .filter(PostLikes.user_id == user_id, PostLikes.post_id == post_id)
        .first()
    )


async def read_comment_like(db: Session, user_id: str, comment_id: int):
    return (
        db.query(CommentLikes)
        .filter(CommentLikes.user_id == user_id, CommentLikes.comment_id == comment_id)
        .first()
    )


async def create_image(db: Session, image: Image, temp_post_id: int):
    image = Images(**image.model_dump(), temp_post_id=temp_post_id)
    db.add(image)
    db.commit()
    return image


async def delete_post(db: Session, post: Posts):
    db.delete(post)
    db.commit()


async def delete_comment(db: Session, comment: Comments):
    comment.post.decrement_comment_count()

    parent_comment = comment.parent_comment
    if parent_comment:
        parent_comment.decrement_child_comment_count()
        if parent_comment.child_comment_count == 0:
            db.delete(parent_comment)
        else:
            db.delete(comment)
    else:
        if comment.child_comment_count == 0:
            db.delete(comment)
        else:
            comment.author_id = None
            comment.content = "삭제된 댓글입니다"
    db.commit()


async def delete_follow(db: Session, follow: Follows):
    db.delete(follow)
    db.commit()


async def modify_user(db: Session, user_id: str, user_profile: UserProfile):
    user = db.query(Users).filter(Users.user_id == user_id).first()
    
    if user_profile.name:
        user.name = user_profile.name

    if user_profile.email:
        user.email = user_profile.email

    if user_profile.image:
        user.image = user_profile.image

    db.commit()
    return user


async def read_notifications(db: Session, user_id: str):
    return db.query(Notifications).filter(Notifications.receiver_id == user_id).all()


async def check_notification(db: Session, notification_id: int):
    notification = (
        db.query(Notifications)
        .filter(Notifications.notification_id == notification_id)
        .first()
    )
    notification.checked = True
    db.commit()
    return notification


async def delete_notifications(db: Session, user_id: str):
    notifications = (
        db.query(Notifications)
        .filter(Notifications.receiver_id == user_id)
        .all()
    )
    for notification in notifications:
        db.delete(notification)
    db.commit()


async def create_chat_history(db: Session, chat_history: ChatHistory):
    chat_history = ChatHistories(**chat_history.model_dump())
    db.add(chat_history)
    db.commit()
    return chat_history


async def read_chat_histories(
    db: Session, sender_id: str, receiver_id: str, last_chat_history_id: int
):
    query = db.query(ChatHistories).filter(
        or_(
            (ChatHistories.sender_id == sender_id)
            & (ChatHistories.receiver_id == receiver_id),
            (ChatHistories.sender_id == receiver_id)
            & (ChatHistories.receiver_id == sender_id),
        )
    )

    query = query.filter(ChatHistories.chat_history_id < last_chat_history_id)

    query = query.order_by(ChatHistories.created_at.desc())
    query = query.limit(100)

    return query.all()[::-1]


async def read_chatting_rooms(db: Session, user_id: str):
    subquery = (
        db.query(func.max(ChatHistories.created_at))
        .filter(
            or_(
                (ChatHistories.sender_id == user_id) & (ChatHistories.receiver_id == Users.user_id),
                (ChatHistories.receiver_id == user_id) & (ChatHistories.sender_id == Users.user_id),
            )
        )
        .correlate(Users)
        .scalar_subquery()
    )

    query = (
        db.query(Users, ChatHistories)
        .join(
            ChatHistories,
            or_(
                (ChatHistories.sender_id == user_id) & (ChatHistories.receiver_id == Users.user_id),
                (ChatHistories.receiver_id == user_id) & (ChatHistories.sender_id == Users.user_id),
            )
        )
        .filter(
            ChatHistories.created_at == subquery
        )
    )

    chatrooms = []
    for user, chat_history in query.all():
        user = UserInfo.model_validate(user)
        chat_history = ChatHistory.model_validate(chat_history)

        chatroom = ChatRoom(opponent=user, last_chat=chat_history)
        chatrooms.append(chatroom)
    
    return chatrooms


async def read_random_design_images(db: Session, n: int):
    return db.query(DesignImages).order_by(func.random()).limit(n).all()


async def read_design_images(db: Session, i: int):
    return db.query(DesignImages).filter(DesignImages.index == i).first()

async def read_item_images(db: Session, color: list):
    return db.query(ItemImages).order_by(ItemImages.color.l2_distance(color)).limit(5).all()