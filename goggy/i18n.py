"""Minimal UI internationalization. English + Hebrew.

Lookup is ``translate(lang, key, **fmt)``. Missing keys fall back to English,
then to the key itself, so a missing translation degrades gracefully rather than
crashing a page.
"""

from __future__ import annotations

LANGUAGES = {"en": "English", "he": "עברית"}
RTL_LANGS = {"he"}
DEFAULT = "en"

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        # nav / chrome
        "home": "Home",
        "new_post": "New post",
        "admin": "Admin",
        "logout": "Log out",
        "settings": "Settings",
        "search_placeholder": "Search…",
        "toggle_theme": "Toggle dark mode",
        "language": "Language",
        "powered_by": "powered by Goggy",
        # index
        "no_posts": "No posts yet.",
        "write_first": "Write the first one.",
        "read_more": "Read more →",
        "newer": "← Newer",
        "older": "Older →",
        "page_x_of_y": "Page {page} of {total}",
        # post
        "min_read": "{n} min read",
        "draft": "Draft",
        "scheduled": "Scheduled",
        "edit": "Edit",
        "history": "History",
        "delete": "Delete",
        "delete_confirm": "Delete this post? This cannot be undone.",
        "contents": "Contents",
        "updated_on": "updated {date}",
        "back_to_posts": "← Back to all posts",
        # search
        "search": "Search",
        "search_button": "Search",
        "results_for": "{n} result(s) for “{q}”.",
        "no_results": "No matching posts.",
        # tag
        "posts_tagged": "Posts tagged",
        "no_posts_tag": "No posts with this tag.",
        "all_posts": "← All posts",
        # login
        "admin_login": "Admin login",
        "password": "Password",
        "log_in": "Log in",
        "incorrect_password": "Incorrect password.",
        "too_many_attempts": "Too many attempts. Try again later.",
        # editor
        "edit_post": "Edit post",
        "title": "Title",
        "tags_label": "Tags (comma-separated)",
        "publish_at_label": "Publish at (blank = now)",
        "insert_image": "Insert image",
        "paste_hint": "Tip: paste images directly with Ctrl/Cmd+V.",
        "markdown": "Markdown",
        "preview": "Preview",
        "save_changes": "Save changes",
        "publish": "Publish",
        "cancel": "Cancel",
        "fullscreen": "Fullscreen",
        "exit_fullscreen": "Exit fullscreen",
        "hide_fields": "Hide fields",
        "show_fields": "Show fields",
        # revisions
        "revision_history": "Revision history",
        "no_revisions": "No earlier versions — this post hasn't been edited yet.",
        "restore": "Restore",
        "restore_confirm": "Restore this version? Current state is snapshotted first.",
        "preview_of": "Preview of {id}",
        "back_to_post": "← Back to post",
        # settings page
        "site_settings": "Site settings",
        "blog_name": "Blog name",
        "tagline": "Tagline",
        "default_language": "Default language",
        "posts_per_page": "Posts per page",
        "footer_text": "Footer text",
        "save": "Save",
        "saved": "Settings saved.",
        # two-factor auth
        "two_factor": "Two-factor authentication",
        "twofa_setup_title": "Set up two-factor authentication",
        "twofa_intro": "Two-factor authentication is required. Scan the QR code with an authenticator app (Google Authenticator, Authy, 1Password…), then enter the 6-digit code to finish.",
        "scan_qr": "Scan this QR code",
        "manual_key": "Or enter this key manually:",
        "enter_code": "Enter the 6-digit code",
        "code": "Code",
        "verify": "Verify",
        "enable_2fa": "Enable two-factor auth",
        "invalid_code": "Invalid code. Try again.",
        "twofa_verify_title": "Two-step verification",
        "twofa_verify_intro": "Enter the 6-digit code from your authenticator app.",
        "use_recovery": "Use a recovery code instead",
        "recovery_code": "Recovery code",
        "recovery_title": "Save your recovery codes",
        "recovery_intro": "Store these somewhere safe. Each code works once if you lose your authenticator. They will not be shown again.",
        "continue": "Continue",
        "twofa_enabled": "Two-factor authentication is enabled.",
        "recovery_remaining": "Recovery codes remaining: {n}",
        "regenerate_recovery": "Regenerate recovery codes",
        "regenerate_warning": "This invalidates your old recovery codes.",
    },
    "he": {
        "home": "בית",
        "new_post": "רשומה חדשה",
        "admin": "מנהל",
        "logout": "התנתקות",
        "settings": "הגדרות",
        "search_placeholder": "חיפוש…",
        "toggle_theme": "מצב כהה",
        "language": "שפה",
        "powered_by": "מופעל על ידי Goggy",
        "no_posts": "אין רשומות עדיין.",
        "write_first": "כתבו את הראשונה.",
        "read_more": "קראו עוד →",
        "newer": "→ חדשות יותר",
        "older": "← ישנות יותר",
        "page_x_of_y": "עמוד {page} מתוך {total}",
        "min_read": "קריאה של {n} דק׳",
        "draft": "טיוטה",
        "scheduled": "מתוזמן",
        "edit": "עריכה",
        "history": "היסטוריה",
        "delete": "מחיקה",
        "delete_confirm": "למחוק את הרשומה? לא ניתן לבטל פעולה זו.",
        "contents": "תוכן עניינים",
        "updated_on": "עודכן ב־{date}",
        "back_to_posts": "→ חזרה לכל הרשומות",
        "search": "חיפוש",
        "search_button": "חיפוש",
        "results_for": "{n} תוצאות עבור ״{q}״.",
        "no_results": "לא נמצאו רשומות תואמות.",
        "posts_tagged": "רשומות מתויגות",
        "no_posts_tag": "אין רשומות עם תגית זו.",
        "all_posts": "→ כל הרשומות",
        "admin_login": "כניסת מנהל",
        "password": "סיסמה",
        "log_in": "כניסה",
        "incorrect_password": "סיסמה שגויה.",
        "too_many_attempts": "יותר מדי ניסיונות. נסו שוב מאוחר יותר.",
        "edit_post": "עריכת רשומה",
        "title": "כותרת",
        "tags_label": "תגיות (מופרדות בפסיקים)",
        "publish_at_label": "מועד פרסום (ריק = עכשיו)",
        "insert_image": "הוספת תמונה",
        "paste_hint": "טיפ: ניתן להדביק תמונות ישירות עם Ctrl/Cmd+V.",
        "markdown": "Markdown",
        "preview": "תצוגה מקדימה",
        "save_changes": "שמירת שינויים",
        "publish": "פרסום",
        "cancel": "ביטול",
        "fullscreen": "מסך מלא",
        "exit_fullscreen": "יציאה ממסך מלא",
        "hide_fields": "הסתר שדות",
        "show_fields": "הצג שדות",
        "revision_history": "היסטוריית גרסאות",
        "no_revisions": "אין גרסאות קודמות — הרשומה טרם נערכה.",
        "restore": "שחזור",
        "restore_confirm": "לשחזר גרסה זו? המצב הנוכחי יישמר תחילה.",
        "preview_of": "תצוגה מקדימה של {id}",
        "back_to_post": "→ חזרה לרשומה",
        "site_settings": "הגדרות האתר",
        "blog_name": "שם הבלוג",
        "tagline": "תיאור",
        "default_language": "שפת ברירת מחדל",
        "posts_per_page": "רשומות בעמוד",
        "footer_text": "טקסט כותרת תחתונה",
        "save": "שמירה",
        "saved": "ההגדרות נשמרו.",
        "two_factor": "אימות דו-שלבי",
        "twofa_setup_title": "הגדרת אימות דו-שלבי",
        "twofa_intro": "אימות דו-שלבי הוא חובה. סרקו את קוד ה-QR באפליקציית אימות (Google Authenticator, Authy, 1Password…), והזינו את הקוד בן 6 הספרות לסיום.",
        "scan_qr": "סרקו את קוד ה-QR",
        "manual_key": "או הזינו מפתח זה ידנית:",
        "enter_code": "הזינו את הקוד בן 6 הספרות",
        "code": "קוד",
        "verify": "אימות",
        "enable_2fa": "הפעלת אימות דו-שלבי",
        "invalid_code": "קוד שגוי. נסו שוב.",
        "twofa_verify_title": "אימות דו-שלבי",
        "twofa_verify_intro": "הזינו את הקוד בן 6 הספרות מאפליקציית האימות.",
        "use_recovery": "השתמשו בקוד שחזור במקום",
        "recovery_code": "קוד שחזור",
        "recovery_title": "שמרו את קודי השחזור",
        "recovery_intro": "שמרו אותם במקום בטוח. כל קוד תקף פעם אחת אם תאבדו את אפליקציית האימות. הם לא יוצגו שוב.",
        "continue": "המשך",
        "twofa_enabled": "אימות דו-שלבי מופעל.",
        "recovery_remaining": "קודי שחזור שנותרו: {n}",
        "regenerate_recovery": "יצירת קודי שחזור חדשים",
        "regenerate_warning": "פעולה זו מבטלת את קודי השחזור הישנים.",
    },
}


def normalize(lang: str | None) -> str:
    return lang if lang in LANGUAGES else DEFAULT


def direction(lang: str) -> str:
    return "rtl" if lang in RTL_LANGS else "ltr"


def translate(lang: str, key: str, **fmt) -> str:
    lang = normalize(lang)
    text = TRANSLATIONS[lang].get(key) or TRANSLATIONS[DEFAULT].get(key) or key
    if fmt:
        try:
            return text.format(**fmt)
        except (KeyError, IndexError):
            return text
    return text
