from app.models.email_outbox import EmailOutbox
from app.models.feedback import Feedback, FeedbackAttachment, FeedbackReply
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
from app.models.meetings import (
    MeetingBooking,
    MeetingBookingRoom,
    MeetingRoom,
)
from app.models.news import (
    News,
    NewsAttachment,
    NewsComment,
    NewsGalleryImage,
    NewsLike,
    NewsPoll,
    NewsPollOption,
    NewsPollVote,
    NewsPollVoter,
    NewsVersion,
)
from app.models.notification import Notification
from app.models.object_directory import (
    ObjectDirectory,
    ObjectDirectoryEntry,
    ObjectEntryContact,
)
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
    "MeetingBooking",
    "MeetingBookingRoom",
    "MeetingRoom",
    "News",
    "NewsAttachment",
    "NewsComment",
    "NewsGalleryImage",
    "NewsLike",
    "NewsPoll",
    "NewsPollOption",
    "NewsPollVote",
    "NewsPollVoter",
    "NewsVersion",
    "Notification",
    "ObjectDirectory",
    "ObjectDirectoryEntry",
    "ObjectEntryContact",
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
