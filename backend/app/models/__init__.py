from app.models.email_outbox import EmailOutbox
from app.models.feedback import Feedback, FeedbackAttachment, FeedbackReply
from app.models.meetings import (
    MeetingBooking,
    MeetingBookingRoom,
    MeetingRoom,
)
from app.models.files import FileFolder, FileFolderPermission
from app.models.kb import (
    KbArticle,
    KbArticleComment,
    KbArticleFeedback,
    KbArticleFile,
    KbArticlePermission,
    KbArticleTag,
    KbArticleVersion,
    KbSection,
    KbSectionPermission,
    KbSuggestion,
    KbTag,
)
from app.models.links import Bookmark, ServiceLink
from app.models.news import News, NewsAttachment, NewsGalleryImage, NewsVersion
from app.models.notification import Notification
from app.models.photos import (
    Photo,
    PhotoFolder,
    PhotoFolderPermission,
    PhotoFolderShareToken,
    PhotoShareToken,
    PhotoTag,
    PhotoTagAssignment,
    PhotoZipJob,
)
from app.models.staff_order import StaffDepartmentOrder
from app.models.user import User
from app.models.user_attribute_mapping import UserAttributeMapping

__all__ = [
    "Bookmark",
    "EmailOutbox",
    "MeetingBooking",
    "MeetingBookingRoom",
    "MeetingRoom",
    "Feedback",
    "FeedbackAttachment",
    "FeedbackReply",
    "FileFolder",
    "FileFolderPermission",
    "KbArticle",
    "KbArticleComment",
    "KbArticleFeedback",
    "KbArticleFile",
    "KbArticlePermission",
    "KbArticleTag",
    "KbArticleVersion",
    "KbSection",
    "KbSectionPermission",
    "KbSuggestion",
    "KbTag",
    "News",
    "NewsAttachment",
    "NewsGalleryImage",
    "NewsVersion",
    "Notification",
    "Photo",
    "PhotoFolder",
    "PhotoFolderPermission",
    "PhotoFolderShareToken",
    "PhotoShareToken",
    "PhotoTag",
    "PhotoTagAssignment",
    "PhotoZipJob",
    "ServiceLink",
    "StaffDepartmentOrder",
    "User",
    "UserAttributeMapping",
]
