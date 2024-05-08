import os
import requests
import shutil
import uuid
import re
from datetime import timedelta, timezone

from fastapi import APIRouter, Depends, UploadFile, status

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError 

from database import crud
from database.models import *
from database.schemas import *
from dependencies import *
from config_loader import config


router = APIRouter(
    prefix="/user",
    tags=["user"]
)


def verify_password(password: str, hashed_password: str):
    return pwd_context.verify(password, hashed_password)


def get_hashed_password(password: str):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: timedelta):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config["TOKEN"]["secret"], algorithm=config["TOKEN"]["algorithm"])
    return encoded_jwt


async def authenticate_user(db: Session, user: UserSignIn):
    user_db = await crud.read_user_by_id(db, user.user_id)
    if not user_db:
        return False
    if not verify_password(user.password, user_db.hashed_password):
        return False
    return user_db


@router.post("/")
async def create_user(user: UserForm, db: Session = Depends(get_db)):
    hashed_password = get_hashed_password(user.password)
    user = HashedUser(**user.model_dump(), hashed_password=hashed_password)

    user_db = await crud.read_user_by_id(db, user.user_id)
    if user_db:
        raise HTTPException(status_code=409, detail="User ID already exists")

    await crud.create_user(db, user)
    return {"message": "User created successfully"}


@router.post("/token", response_model=TokenResult)
async def generate_token(user: UserSignIn, db: Session = Depends(get_db)):
    user = await authenticate_user(db, user)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    data = {"sub": user.user_id}
    access_token_expires = timedelta(minutes=int(config["TOKEN"]["expire_minutes"]))
    access_token = create_access_token(data=data, expires_delta=access_token_expires)
    return {"user": user, "access_token": access_token}


@router.post("/token/{access_token}", response_model=TokenResult)
async def generate_token_from_external_provider(
    access_token: str, provider: str, user: UserInfo, db: Session = Depends(get_db)
):
    if provider == "google":
        response = requests.get(
            "https://www.googleapis.com/oauth2/v1/tokeninfo",
            params={"access_token": access_token},
        )
    elif provider == "kakao":
        response = requests.get(
            "https://kapi.kakao.com/v1/user/access_token_info",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    elif provider == "naver":
        response = requests.get(
            "https://openapi.naver.com/v1/nid/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    else:
        raise HTTPException(status_code=501, detail="Provider not supported")

    if not response.ok:
        raise HTTPException(status_code=401, detail="Invalid access token")

    user_external_map = await crud.read_user_external_map(db, user.user_id, provider)
    if user_external_map:
        user = user_external_map.user
    else:
        internal_id = str(uuid.uuid4())
        user_external_map = UserExternalMap(
            external_id=user.user_id, provider=provider, user_id=internal_id
        )
        user.user_id = internal_id

        try:
            await crud.create_user(db, user)
        except IntegrityError as e:
            error_message = e.orig.diag.message_detail
            pattern = r"\((.*?)\)=\((.*?)\)"
            matched = re.search(pattern, error_message)
            key = matched.group(1)

            if key == "email":
                raise HTTPException(status_code=409, detail="Email already registerd")
        except Exception as e:
            print(e)
            raise HTTPException(status_code=500, detail="Internal server error")

        await crud.create_user_external_map(db, user_external_map)

    data = {"sub": user.user_id}
    access_token_expires = timedelta(minutes=int(config["TOKEN"]["expire_minutes"]))
    access_token = create_access_token(data=data, expires_delta=access_token_expires)
    return {"user": user, "access_token": access_token}


@router.get("/me", response_model=UserInfoView)
async def current_user(
    user_id: str = Depends(get_current_user), db: Session = Depends(get_db)
):
    user = await crud.read_user_by_id(db, user_id)

    user_info = UserInfoView.model_validate(user)
    user_info.followee_count = len(user.followees)
    user_info.follower_count = len(user.followers)

    return user_info
    

@router.get("/profile/{user_id}", response_model=UserInfoView)
async def get_user_profile(user_id: str, signed_in_user_id: str | None = Depends(get_current_user_if_signed_in), db: Session = Depends(get_db)):
    user = await crud.read_user_by_id(db, user_id, signed_in_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found!!")

    user_info = UserInfoView.model_validate(user)
    user_info.followee_count = len(user.followees)
    user_info.follower_count = len(user.followers)

    return user_info


@router.post("/follower/{user_id}", response_model=list[UserInfo])
async def get_followers(
    user_id: str, db: Session = Depends(get_db)
):
    user = await crud.read_user_by_id(db, user_id)
    return user.followers


@router.post("/followee/{user_id}", response_model=list[UserInfo])
async def get_followees(
    user_id: str, db: Session = Depends(get_db)
):
    user = await crud.read_user_by_id(db, user_id)
    return user.followees


@router.get("/scrapped_post", response_model=list[PostPreview])
async def get_scrapped_posts(
    user_id: str = Depends(get_current_user), db: Session = Depends(get_db)
):
    posts = await crud.search_posts(db, user_id=user_id, scrapped=True)
    return posts


@router.put("/modification", response_model=UserInfo)
async def modify_user_profile(
    user_profile: UserProfile,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = await crud.modify_user(db, user_id, user_profile)
    return user


@router.put("/modification/profile_image", response_model=UserInfo)
async def modify_user_profile_image(
    file: UploadFile,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    upload_path = config["PATH"]["upload"]
    filename = file.filename
    file_extension = os.path.splitext(filename)[1]
    file_path = os.path.join(upload_path, str(uuid.uuid4()) + file_extension)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    image_id = config["URL"]["api_url"] + "/" + file_path
    user_profile = UserProfile(image=image_id)
    user = await crud.modify_user(db, user_id, user_profile)
    return user


@router.get("/notification", response_model=list[Notification])
async def get_notifications(
    user_id: str = Depends(get_current_user), db: Session = Depends(get_db)
):
    notifications = await crud.read_notifications(db, user_id)
    return notifications


@router.post("/notification/{notification_id}", response_model=Notification)
async def check_notification(
    notification_id: int,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = await crud.check_notification(db, notification_id)
    return notification


@router.delete("/notification")
async def delete_notification(
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    await crud.delete_notifications(db, user_id)
    return {"message": "Notification deleted successfully"}

@router.post("/password")
async def get_user_password(user_id: str, db: Session = Depends(get_db)):
    user = await crud.read_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {"user_id": user.user_id, "password": user.hashed_password}
