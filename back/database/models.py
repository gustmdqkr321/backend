from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Sequence, DateTime
from sqlalchemy.ext.hybrid import hybrid_method, hybrid_property
from sqlalchemy.orm import relationship, query_expression, Mapped, mapped_column
from pgvector.sqlalchemy import Vector
from database.database import Base
from datetime import datetime
from typing import Optional


class Follows(Base):
    __tablename__ = "follows"

    follower_user_id = Column(String, ForeignKey("users.user_id"), primary_key=True)
    followee_user_id = Column(String, ForeignKey("users.user_id"), primary_key=True)


class Users(Base):
    __tablename__ = "users"

    user_id = Column(String, primary_key=True, index=True)

    name = Column(String)
    email = Column(String, unique=True)
    image = Column(String)
    hashed_password = Column(String)
    embedding = Column(Vector(8192))

    posts = relationship("Posts", back_populates="author", uselist=True)
    comments = relationship("Comments", back_populates="author", uselist=True)
    scrapped_posts = relationship(
        "Posts",
        secondary="post_scraps",
        back_populates="scrappers",
        cascade="all, delete",
        uselist=True,
    )
    liked_posts = relationship(
        "Posts",
        secondary="post_likes",
        back_populates="likers",
        cascade="all, delete",
        uselist=True,
    )
    liked_comments = relationship(
        "Comments",
        secondary="comment_likes",
        back_populates="likers",
        cascade="all, delete",
        uselist=True,
    )
    user_external_map = relationship("UserExternalMapping")
    followers = relationship(
        "Users",
        secondary="follows",
        primaryjoin=user_id == Follows.followee_user_id,
        secondaryjoin=user_id == Follows.follower_user_id,
        backref="followees",
        cascade="all, delete",
        uselist=True,
    )
    notifications = relationship(
        "Notifications", back_populates="receiver", cascade="all, delete", uselist=True
    )
    sended_chat = relationship(
        "ChatHistories", foreign_keys="ChatHistories.sender_id", back_populates="sender", cascade="all, delete", uselist=True
    )
    received_chat = relationship(
        "ChatHistories", foreign_keys="ChatHistories.receiver_id", back_populates="receiver", cascade="all, delete", uselist=True
    )

    followed: Mapped[Optional[bool]] = query_expression()


class Posts(Base):
    __tablename__ = "posts"

    post_id = Column(Integer, Sequence("post_id_seq"), primary_key=True)

    author_id = Column(String, ForeignKey("users.user_id"), nullable=False)

    title = Column(String, nullable=False)
    content = Column(String, nullable=False)
    category = Column(String, nullable=False)

    scrap_count = Column(Integer, default=0, nullable=False)
    like_count = Column(Integer, default=0, nullable=False)
    view_count = Column(Integer, default=0, nullable=False)
    comment_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    author = relationship("Users", back_populates="posts")
    comments = relationship(
        "Comments",
        primaryjoin="and_(Posts.post_id == Comments.post_id, Comments.parent_comment_id == None)",
        back_populates="post",
        cascade="all, delete-orphan",
        uselist=True,
    )
    scrappers = relationship(
        "Users",
        secondary="post_scraps",
        back_populates="scrapped_posts",
        cascade="all, delete",
        uselist=True,
    )
    likers = relationship(
        "Users",
        secondary="post_likes",
        back_populates="liked_posts",
        cascade="all, delete",
        uselist=True,
    )
    images = relationship("Images", cascade="all, delete-orphan")
    scrapped: Mapped[Optional[bool]] = query_expression()
    liked: Mapped[Optional[bool]] = query_expression()

    @hybrid_method
    def increment_view_count(self):
        self.view_count += 1

    @hybrid_method
    def increment_scrap_count(self):
        self.scrap_count += 1

    @hybrid_method
    def increment_like_count(self):
        self.like_count += 1

    @hybrid_method
    def increment_comment_count(self):
        self.comment_count += 1

    @hybrid_method
    def decrement_comment_count(self):
        self.comment_count -= 1

    @hybrid_property
    def thumbnail(self):
        if self.images:
            return self.images[0]
        else:
            return {
                "image_id": "/images/default/default_thumbnail.png",
                "filename": "default_thumbnail.png",
            }


class Comments(Base):
    __tablename__ = "comments"

    comment_id = Column(Integer, Sequence("comment_id_seq"), primary_key=True)

    author_id = Column(String, ForeignKey("users.user_id"))
    post_id = Column(Integer, ForeignKey("posts.post_id"), nullable=False)
    parent_comment_id = Column(Integer, ForeignKey("comments.comment_id"))

    content = Column(String, nullable=False)
    like_count = Column(Integer, default=0, nullable=False)
    child_comment_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    author = relationship("Users", back_populates="comments")
    post = relationship("Posts", back_populates="comments")
    parent_comment = relationship(
        "Comments",
        remote_side=[comment_id],
        back_populates="child_comments",
    )
    child_comments = relationship(
        "Comments",
        back_populates="parent_comment",
        uselist=True,
        cascade="all, delete-orphan",
    )
    likers = relationship(
        "Users",
        secondary="comment_likes",
        back_populates="liked_comments",
        cascade="all, delete",
        uselist=True,
    )

    @hybrid_method
    def increment_child_comment_count(self):
        self.child_comment_count += 1

    @hybrid_method
    def decrement_child_comment_count(self):
        self.child_comment_count -= 1

    @hybrid_method
    def increment_like_count(self):
        self.like_count += 1


class PostScraps(Base):
    __tablename__ = "post_scraps"

    user_id = Column(String, ForeignKey("users.user_id"), primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.post_id"), primary_key=True)


class PostLikes(Base):
    __tablename__ = "post_likes"

    user_id = Column(String, ForeignKey("users.user_id"), primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.post_id"), primary_key=True)


class CommentLikes(Base):
    __tablename__ = "comment_likes"

    user_id = Column(String, ForeignKey("users.user_id"), primary_key=True)
    comment_id = Column(Integer, ForeignKey("comments.comment_id"), primary_key=True)


class TempPosts(Base):
    __tablename__ = "temp_posts"

    temp_post_id = Column(Integer, Sequence("temp_post_id_seq"), primary_key=True)

    author_id = Column(String, ForeignKey("users.user_id"), unique=True)

    images = relationship("Images", cascade="all, delete-orphan")
    author = relationship("Users")


class Images(Base):
    __tablename__ = "images"

    image_id = Column(String, primary_key=True)

    temp_post_id = Column(Integer, ForeignKey("temp_posts.temp_post_id"))
    post_id = Column(Integer, ForeignKey("posts.post_id"))
    filename = Column(String, nullable=False)


class UserExternalMapping(Base):
    __tablename__ = "user_external_mapping"

    external_id = Column(String, primary_key=True)
    provider = Column(String, primary_key=True)

    user_id = Column(String, ForeignKey("users.user_id"), nullable=False)

    user = relationship("Users", back_populates="user_external_map")


class Notifications(Base):
    __tablename__ = "notifications"

    notification_id = Column(Integer, Sequence("notification_id_seq"), primary_key=True)
    receiver_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    reference_id = Column(Integer, ForeignKey("posts.post_id"), nullable=True)

    content = Column(String, nullable=False)
    checked = Column(Boolean, default=False, nullable=False)
    category = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    
    receiver = relationship("Users", back_populates="notifications")


class ChatHistories(Base):
    __tablename__ = "chat_histories"

    chat_history_id = Column(
        Integer, Sequence("chat_histories_id_seq"), primary_key=True
    )
    sender_id = Column(String, ForeignKey("users.user_id"), nullable=False)
    receiver_id = Column(String, ForeignKey("users.user_id"), nullable=False)

    message = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False)

    sender = relationship("Users", foreign_keys=[sender_id], back_populates="sended_chat")
    receiver = relationship("Users", foreign_keys=[receiver_id], back_populates="received_chat")


class DesignImages(Base):
    __tablename__ = "design_images"

    filename = Column(String, primary_key=True)

    index = Column(Integer, nullable=True)
    src_url = Column(String, unique=True)
    landing = Column(String, nullable=False)


class ItemImages(Base):
    __tablename__ = "item_images"

    name = Column(String, primary_key=True)

    src_url = Column(String, unique=True)
    landing = Column(String, nullable=False)
    color = Column(Vector(3))
    category_id = Column(Integer)
