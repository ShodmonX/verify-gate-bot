from html import escape


WELCOME_TEXT = (
    "Salom {MENTION}! Guruhga xush kelibsiz!\n\n"
    "Siz hozir guruhda faqat o'qiy olasiz. Yozish imkoniyatiga ega bo'lish uchun "
    "quyidagi tugmani bosing va qoidalarga roziligingizni bildiring"
)

ALERT_TEXT = (
    "Qo'lingiz bilmasdan boshqa joyga tegib\n"
    "ketdi ;)\n\n"
    "Shoshmang, hali sizgayam boshqa biror\n"
    "tugma jo'natarmiz boshinga."
)

REMINDER_TEXT = (
    "⚠️ {MENTION} qoidalarga shu paytgacha rozilik bildirmagan ko'rinadi. "
    "Iltimos, quyidagi tugmani bosing va so'ralgan topshiriqni bajaring. "
    "Undan keyin sizga shu guruhda yozish imkoniyatini beramiz;)"
)

RULES_TEXT = (
    "Python guruhida ushbu qoidalarga qat'iy amal qiling:\n\n"
    " - botlar haqida gaplashish;\n"
    " - pythonga aloqasi bo'lmagan mavzularda gaplashish;\n"
    " - odob-axloq qoidalariga zid mazmundagi gap-so'zlar;\n"
    " - guruhga ruxsatsiz bot qo'shish;\n"
    " - guruhga kanal, guruh, bot yoki boshqa mahsulotlar reklamasini jo'natish;\n"
    " - xabar ustiga chiqib ketadigan darajadagi belgilarning nikingiz (Telegramdagi "
    "taxallusingiz) ga yozilishi taqiqlanadi (Bu guruhda o'qish samaradorligini "
    "oshirish uchun, iltimos, buni jiddiy qabul qiling).\n\n"
    "Agar shu qoidalarga rozi bo'lsangiz hoziroq {WORD} so'zini yozib jo'nating. "
    "Unutmang, qoidaga qarshi har qanday harakat jazoga olib kelishi mumkin."
)

SUCCESS_TEXT = (
    "Safimizda yangi a'zo bor!\n"
    "Hozirgina {MENTION} guruh qoidalariga rozilik bildirdi"
)

DM_SUCCESS_TEXT = (
    "Qoidalarga rozilik bildirganingiz uchun rahmat. Endi guruhda xabar yubora olasiz."
)


def html_mention(user_id: int, display_name: str) -> str:
    safe_name = escape(display_name)
    return f"<a href=\"tg://user?id={user_id}\">{safe_name}</a>"


def render_welcome(user_id: int, display_name: str) -> str:
    return WELCOME_TEXT.format(MENTION=html_mention(user_id, display_name))


def render_reminder(user_id: int, display_name: str) -> str:
    return REMINDER_TEXT.format(MENTION=html_mention(user_id, display_name))


def render_success(user_id: int, display_name: str) -> str:
    return SUCCESS_TEXT.format(MENTION=html_mention(user_id, display_name))


def render_rules(word: str) -> str:
    return RULES_TEXT.format(WORD=f"<b>{escape(word)}</b>")
