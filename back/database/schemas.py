from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime


class UserSignIn(BaseModel):
    user_id: str
    password: str


class UserProfile(BaseModel):
    name: str | None = None
    email: str | None = None
    image: str | None = None


class UserInfo(UserProfile):
    user_id: str
    followed: bool | None = None

    model_config = ConfigDict(from_attributes=True)


class UserInfoView(UserInfo):
    follower_count: int | None = None
    followee_count: int | None = None

    model_config = ConfigDict(from_attributes=True)


class UserForm(UserSignIn, UserInfo): ...


class HashedUser(UserInfo):
    user_id: str
    hashed_password: str | None = None


class UserExternalMap(BaseModel):
    external_id: str
    provider: str
    user_id: str


class TokenResult(BaseModel):
    user: UserInfo
    access_token: str


class CommentForm(BaseModel):
    post_id: int
    parent_comment_id: int | None = None
    content: str


class Comment(CommentForm):
    comment_id: int
    like_count: int
    created_at: datetime
    child_comments: list[Comment] | None = None
    author: UserInfo | None = None


class PostForm(BaseModel):
    title: str
    category: str
    content: str


class BasePost(BaseModel): 
    post_id: int
    title: str
    category: str
    scrap_count: int
    like_count: int
    view_count: int
    comment_count: int
    created_at: datetime
    author: UserInfo
    scrapped: bool
    liked: bool


class Image(BaseModel):
    image_id: str
    filename: str

    model_config = ConfigDict(from_attributes=True)


class PostPreview(BasePost):
    thumbnail: Image | None = None

    model_config = ConfigDict(from_attributes=True)


class Post(BasePost):
    images: list[Image] | None = None
    content: str

    model_config = ConfigDict(from_attributes=True)


class TempPost(BaseModel):
    temp_post_id: int


class Notification(BaseModel):
    notification_id: int
    reference_id: int | None = None
    content: str
    category: str | None = None
    checked: bool


class BaseChatHistory(BaseModel):
    sender_id: str
    receiver_id: str
    message: str
    created_at: datetime = Field(default_factory=datetime.now)

    model_config = ConfigDict(from_attributes=True)


class ChatHistory(BaseChatHistory):
    chat_history_id: int | None = None


class ChatRoom(BaseModel):
    opponent: UserInfo
    last_chat: ChatHistory


class DesignImage(BaseModel):
    index: int
    src_url: str
    landing: str


class RatedImage(BaseModel):
    index: int
    rating: int


class ItemImage(BaseModel):
    name: str
    src_url: str
    landing: str
    
    model_config = ConfigDict(from_attributes=True)