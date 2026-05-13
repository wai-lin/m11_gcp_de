from __future__ import annotations
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class RapidApiModel(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class RapidApiLogPb(RapidApiModel):
    impr_id: str | None = None


class RapidApiExtra(RapidApiModel):
    fatal_item_ids: list[Any] = Field(default_factory=list)
    logid: str | None = None
    now: int | None = None


class RapidApiShareMeta(RapidApiModel):
    desc: str | None = None
    title: str | None = None


class RapidApiBioLink(RapidApiModel):
    link: str | None = None
    risk: int | None = None


class RapidApiCommerceUserInfo(RapidApiModel):
    commerceUser: bool | None = None


class RapidApiProfileTab(RapidApiModel):
    showMusicTab: bool | None = None
    showPlayListTab: bool | None = None


class RapidApiUserStats(RapidApiModel):
    diggCount: int | None = None
    followerCount: int | None = None
    followingCount: int | None = None
    friendCount: int | None = None
    heart: int | None = None
    heartCount: int | None = None
    videoCount: int | None = None


class RapidApiUserProfile(RapidApiModel):
    UserStoryStatus: int | None = None
    avatarLarger: str | None = None
    avatarMedium: str | None = None
    avatarThumb: str | None = None
    bioLink: RapidApiBioLink | None = None
    canExpPlaylist: bool | None = None
    commentSetting: int | None = None
    commerceUserInfo: RapidApiCommerceUserInfo | None = None
    downloadSetting: int | None = None
    duetSetting: int | None = None
    followingVisibility: int | None = None
    ftc: bool | None = None
    id: str | None = None
    isADVirtual: bool | None = None
    isEmbedBanned: bool | None = None
    nickNameModifyTime: int | None = None
    nickname: str | None = None
    openFavorite: bool | None = None
    privateAccount: bool | None = None
    profileEmbedPermission: int | None = None
    profileTab: RapidApiProfileTab | None = None
    relation: int | None = None
    secUid: str | None = None
    secret: bool | None = None
    signature: str | None = None
    stitchSetting: int | None = None
    ttSeller: bool | None = None
    uniqueId: str | None = None
    verified: bool | None = None


class RapidApiUserInfo(RapidApiModel):
    stats: RapidApiUserStats | None = None
    statsV2: RapidApiUserStats | None = None
    user: RapidApiUserProfile | None = None


class RapidApiUserInfoResponse(RapidApiModel):
    extra: RapidApiExtra | None = None
    log_pb: RapidApiLogPb | None = None
    shareMeta: RapidApiShareMeta | None = None
    statusCode: int | None = None
    status_code: int | None = None
    status_msg: str | None = None
    userInfo: RapidApiUserInfo | None = None


class RapidApiAuthorStats(RapidApiUserStats):
    pass


class RapidApiItemControl(RapidApiModel):
    can_comment: bool | None = None
    can_repost: bool | None = None
    can_share: bool | None = None


class RapidApiMusic(RapidApiModel):
    album: str | None = None
    authorName: str | None = None
    title: str | None = None


class RapidApiVideo(RapidApiModel):
    VQScore: str | None = None


class RapidApiPostAuthor(RapidApiUserProfile):
    pass


class RapidApiPost(RapidApiModel):
    AIGCDescription: str | None = None
    CategoryType: int | None = None
    HasPromoteEntry: int | None = None
    adAuthorization: bool | None = None
    author: RapidApiPostAuthor | None = None
    authorStats: RapidApiAuthorStats | None = None
    backendSourceEventTracking: str | None = None
    challenges: list[Any] = Field(default_factory=list)
    collected: bool | None = None
    contents: list[Any] = Field(default_factory=list)
    createTime: int | None = None
    desc: str | None = None
    digged: bool | None = None
    diversificationId: int | None = None
    duetDisplay: int | None = None
    duetEnabled: bool | None = None
    forFriend: bool | None = None
    id: str | None = None
    isAd: bool | None = None
    itemCommentStatus: int | None = None
    item_control: RapidApiItemControl | None = None
    maskType: int | None = None
    music: RapidApiMusic | None = None
    officalItem: bool | None = None
    originalItem: bool | None = None
    privateItem: bool | None = None
    secret: bool | None = None
    shareEnabled: bool | None = None
    stats: RapidApiUserStats | None = None
    statsV2: RapidApiUserStats | None = None
    stitchDisplay: int | None = None
    stitchEnabled: bool | None = None
    textExtra: list[Any] = Field(default_factory=list)
    textLanguage: str | None = None
    textTranslatable: bool | None = None
    video: RapidApiVideo | None = None


class RapidApiUserPostsData(RapidApiModel):
    cursor: str | None = None
    extra: RapidApiExtra | None = None
    hasMore: bool | None = None
    itemList: list[RapidApiPost] = Field(default_factory=list)
    log_pb: RapidApiLogPb | None = None
    statusCode: int | None = None
    status_code: int | None = None
    status_msg: str | None = None


class RapidApiUserPostsResponse(RapidApiModel):
    data: RapidApiUserPostsData | None = None


__all__ = [
    "RapidApiAuthorStats",
    "RapidApiBioLink",
    "RapidApiCommerceUserInfo",
    "RapidApiExtra",
    "RapidApiItemControl",
    "RapidApiLogPb",
    "RapidApiModel",
    "RapidApiMusic",
    "RapidApiPost",
    "RapidApiPostAuthor",
    "RapidApiProfileTab",
    "RapidApiShareMeta",
    "RapidApiUserInfo",
    "RapidApiUserInfoResponse",
    "RapidApiUserPostsData",
    "RapidApiUserPostsResponse",
    "RapidApiUserProfile",
    "RapidApiUserStats",
    "RapidApiVideo",
]
