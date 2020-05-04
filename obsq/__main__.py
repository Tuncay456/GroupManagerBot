import datetime
import importlib
import re
from typing import Optional, List

from telegram import Message, Chat, Update, Bot, User
from telegram import ParseMode, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from telegram.error import Unauthorized, BadRequest, TimedOut, NetworkError, ChatMigrated, TelegramError
from telegram.ext import CommandHandler, Filters, MessageHandler, CallbackQueryHandler
from telegram.ext.dispatcher import run_async, DispatcherHandlerStop, Dispatcher
from telegram.utils.helpers import escape_markdown

from haruka import dispatcher, updater, TOKEN, WEBHOOK, SUDO_USERS, OWNER_ID, CERT_PATH, PORT, URL, LOGGER, \
    ALLOW_EXCL
# needed to dynamically load modules
# NOTE: Module order is not guaranteed, specify that in the config file!
from obsq.modules import ALL_MODULES
from obsq.modules.helper_funcs.chat_status import is_user_admin
from obsq.modules.helper_funcs.misc import paginate_modules
from obsq.modules.translations.strings import tld, tld_help 
from obsq.modules.connection import connected


PM_START = """Hello {}, my name is {}!
You know how f*cking hard it is sometimes to manage your Channels/Groups so here is the solution for you
I'm kyne : Telegram bot that helps you manage your Channel/Groups.

Created by : [obsq](t.me/obsquriel)

Click /help or Help button below to find out more about kyne and how to use kyne at it's best.
"""


IMPORTED = {}
MIGRATEABLE = []
HELPABLE = {}
STATS = []
USER_INFO = []
DATA_IMPORT = []
DATA_EXPORT = []

CHAT_SETTINGS = {}
USER_SETTINGS = {}

GDPR = []

for module_name in ALL_MODULES:
    imported_module = importlib.import_module("obsq.modules." + module_name)
    if not hasattr(imported_module, "__mod_name__"):
        imported_module.__mod_name__ = imported_module.__name__

    if not imported_module.__mod_name__.lower() in IMPORTED:
        IMPORTED[imported_module.__mod_name__.lower()] = imported_module
    else:
        raise Exception("Can't have two modules with the same name! Please change one")

    if hasattr(imported_module, "__help__") and imported_module.__help__:
        HELPABLE[imported_module.__mod_name__.lower()] = imported_module

    #Chats to migrate on chat_migrated events
    if hasattr(imported_module, "__migrate__"):
        MIGRATEABLE.append(imported_module)

    if hasattr(imported_module, "__stats__"):
        STATS.append(imported_module)

    if hasattr(imported_module, "__gdpr__"):
        GDPR.append(imported_module)

    if hasattr(imported_module, "__user_info__"):
        USER_INFO.append(imported_module)

    if hasattr(imported_module, "__import_data__"):
        DATA_IMPORT.append(imported_module)

    if hasattr(imported_module, "__export_data__"):
        DATA_EXPORT.append(imported_module)

    if hasattr(imported_module, "__chat_settings__"):
        CHAT_SETTINGS[imported_module.__mod_name__.lower()] = imported_module

    if hasattr(imported_module, "__user_settings__"):
        USER_SETTINGS[imported_module.__mod_name__.lower()] = imported_module


#Do NOT async this!
def send_help(chat_id, text, keyboard=None):
    if not keyboard:
        keyboard = InlineKeyboardMarkup(paginate_modules(chat_id, 0, HELPABLE, "help"))
    dispatcher.bot.send_message(chat_id=chat_id,
                                text=text,
                                parse_mode=ParseMode.MARKDOWN,
                                reply_markup=keyboard)


@run_async
def test(bot: Bot, update: Update):
    #pprint(eval(str(update)))
    #update.effective_message.reply_text("Hola tester! _I_ *have* `markdown`", parse_mode=ParseMode.MARKDOWN)
    update.effective_message.reply_text("This person edited a message")
    print(update.effective_message)


@run_async
def start(bot: Bot, update: Update, args: List[str]):
    LOGGER.info("Start")
    chat = update.effective_chat  # type: Optional[Chat]
    #query = update.callback_query #Unused variable
    if update.effective_chat.type == "private":
        if len(args) >= 1:
            if args[0].lower() == "help":
                send_help(update.effective_chat.id, tld(chat.id, "send-help").format(
                     dispatcher.bot.first_name, "" if not ALLOW_EXCL else tld(
                         chat.id, "\nAll commands can either be used with `/` or `!`.\n"
                             )))

            elif args[0].lower().startswith("stngs_"):
                match = re.match("stngs_(.*)", args[0].lower())
                chat = dispatcher.bot.getChat(match.group(1))

                if is_user_admin(chat, update.effective_user.id):
                    send_settings(match.group(1), update.effective_user.id, update, user=False)
                else:
                    send_settings(match.group(1), update.effective_user.id, update, user=True)

            elif args[0][1:].isdigit() and "rules" in IMPORTED:
                IMPORTED["rules"].send_rules(update, args[0], from_pm=True)

            elif args[0].lower() == "controlpanel":
                control_panel(bot, update)
        else:
            send_start(bot, update)
    else:
        update.effective_message.reply_text("I'm f*cking alive")

def send_start(bot, update):
    #Try to remove old message
    try:
        query = update.callback_query
        query.message.delete()
    except:
        pass

    chat = update.effective_chat  # type: Optional[Chat]
    first_name = update.effective_user.first_name 
    text = PM_START

    keyboard = [[InlineKeyboardButton(text="🇮🇳 Language", callback_data="set_lang_")]]
    keyboard += [[InlineKeyboardButton(text="🛠 Reporting", callback_data="cntrl_panel_M"), 
        InlineKeyboardButton(text="❔ Help", callback_data="help_back")]]

    update.effective_message.reply_text(PM_START.format(escape_markdown(first_name), bot.first_name), reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True, parse_mode=ParseMode.MARKDOWN)


def control_panel(bot, update):
    LOGGER.info("Control panel")
    chat = update.effective_chat
    user = update.effective_user

    # ONLY send help in PM
    if chat.type != chat.PRIVATE:

        update.effective_message.reply_text("Contact me in PM to access the control panel.",
                                            reply_markup=InlineKeyboardMarkup(
                                                [[InlineKeyboardButton(text="Control Panel",
                                                                       url=f"t.me/{bot.username}?start=controlpanel")]]))
        return

    #Support to run from command handler
    query = update.callback_query
    if query:
        query.message.delete()

        M_match = re.match(r"cntrl_panel_M", query.data)
        U_match = re.match(r"cntrl_panel_U", query.data)
        G_match = re.match(r"cntrl_panel_G", query.data)
        back_match = re.match(r"help_back", query.data)

        LOGGER.info(query.data)
    else:
        M_match = "kyne : none of a kind" #LMAO, don't uncomment

    if M_match:
        text = "*Control panel* 🛠"

        keyboard = [[InlineKeyboardButton(text="👤 My settings", callback_data="cntrl_panel_U(1)")]]

        #Show connected chat and add chat settings button
        conn = connected(bot, update, chat, user.id, need_admin=False)

        if conn:
            chatG = bot.getChat(conn)
            #admin_list = chatG.get_administrators() #Unused variable

            #If user admin
            member = chatG.get_member(user.id)
            if member.status in ('administrator', 'creator'):
                text += f"\nConnected chat - *{chatG.title}* (you {member.status})"
                keyboard += [[InlineKeyboardButton(text="👥 Group settings", callback_data="cntrl_panel_G_back")]]
            elif user.id in SUDO_USERS:
                text += f"\nConnected chat - *{chatG.title}* (you sudo)"
                keyboard += [[InlineKeyboardButton(text="👥 Group settings (SUDO)", callback_data="cntrl_panel_G_back")]]
            else:
                text += f"\nConnected chat - *{chatG.title}* (you aren't an admin!)"
        else:
            text += "\nNo chat connected!"

        keyboard += [[InlineKeyboardButton(text="Back", callback_data="bot_start")]]

        update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    elif U_match:

        mod_match = re.match(r"cntrl_panel_U_module\((.+?)\)", query.data)
        back_match = re.match(r"cntrl_panel_U\((.+?)\)", query.data)

        chatP = update.effective_chat  # type: Optional[Chat]
        if mod_match:
            module = mod_match.group(1)

            R = CHAT_SETTINGS[module].__user_settings__(bot, update, user)

            text = "You has the following settings for the *{}* module:\n\n".format(
                CHAT_SETTINGS[module].__mod_name__) + R[0]

            keyboard = R[1]
            keyboard += [[InlineKeyboardButton(text="Back", callback_data="cntrl_panel_U(1)")]]
                
            query.message.reply_text(text=text, arse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

        elif back_match:
            text = "*User control panel* 🛠"
            
            query.message.reply_text(text=text, parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup(paginate_modules(user.id, 0, USER_SETTINGS, "cntrl_panel_U")))

    elif G_match:
        mod_match = re.match(r"cntrl_panel_G_module\((.+?)\)", query.data)
        prev_match = re.match(r"cntrl_panel_G_prev\((.+?)\)", query.data)
        next_match = re.match(r"cntrl_panel_G_next\((.+?)\)", query.data)
        back_match = re.match(r"cntrl_panel_G_back", query.data)

        chatP = chat
        conn = connected(bot, update, chat, user.id)

        if not conn == False:
            chat = bot.getChat(conn)
        else:
            query.message.reply_text(text="Error with connection to chat")
            exit(1)

        if mod_match:
            module = mod_match.group(1)
            R = CHAT_SETTINGS[module].__chat_settings__(bot, update, chat, chatP, user)

            if type(R) is list:
                text = R[0]
                keyboard = R[1]
            else:
                text = R
                keyboard = []

            text = "*{}* has the following settings for the *{}* module:\n\n".format(
                escape_markdown(chat.title), CHAT_SETTINGS[module].__mod_name__) + text

            keyboard += [[InlineKeyboardButton(text="Back", callback_data="cntrl_panel_G_back")]]
                
            query.message.reply_text(text=text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(keyboard))

        elif prev_match:
            chat_id = prev_match.group(1)
            curr_page = int(prev_match.group(2))
            chat = bot.get_chat(chat_id)
            query.message.reply_text(tld(user.id, "send-group-settings").format(chat.title),
                                    reply_markup=InlineKeyboardMarkup(
                                        paginate_modules(curr_page - 1, 0, CHAT_SETTINGS, "cntrl_panel_G",
                                                        chat=chat_id)))

        elif next_match:
            chat_id = next_match.group(1)
            next_page = int(next_match.group(2))
            chat = bot.get_chat(chat_id)
            query.message.reply_text(tld(user.id, "send-group-settings").format(chat.title),
                                    reply_markup=InlineKeyboardMarkup(
                                        paginate_modules(next_page + 1, 0, CHAT_SETTINGS, "cntrl_panel_G",
                                                        chat=chat_id)))

        elif back_match:
            text = "Test"
            query.message.reply_text(text=text, parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup(paginate_modules(user.id, 0, CHAT_SETTINGS, "cntrl_panel_G")))


# for test purposes
def error_callback(bot, update, error):
    try:
        raise error
    except Unauthorized:
        LOGGER.warning("NO NONO1")
        LOGGER.warning(error)
        # remove update.message.chat_id from conversation list
    except BadRequest:
        LOGGER.warning("NO NONO2")
        LOGGER.warning("BadRequest caught")
        LOGGER.warning(error)

        # handle malformed requests - read more below!
    except TimedOut:
        LOGGER.warning("NO NONO3")
        # handle slow connection problems
    except NetworkError:
        LOGGER.warning("NO NONO4")
        # handle other connection problems
    except ChatMigrated as err:
        LOGGER.warning("NO NONO5")
        LOGGER.warning(err)
        # the chat_id of a group has changed, use e.new_chat_id instead
    except TelegramError:
        LOGGER.warning(error)
        # handle all other telegram related errors


@run_async
def help_button(bot: Bot, update: Update):
    query = update.callback_query
    chat = update.effective_chat  # type: Optional[Chat]
    mod_match = re.match(r"help_module\((.+?)\)", query.data)
    prev_match = re.match(r"help_prev\((.+?)\)", query.data)
    next_match = re.match(r"help_next\((.+?)\)", query.data)
    back_match = re.match(r"help_back", query.data)
    try:
        if mod_match:
            module = mod_match.group(1)
            mod_name = tld(chat.id, HELPABLE[module].__mod_name__)
            help_txt = tld_help(chat.id, HELPABLE[module].__mod_name__)

            if help_txt == False:
                help_txt = HELPABLE[module].__help__

            text = tld(chat.id, "Here is the help for the *{}* module:\n{}").format(mod_name, help_txt)
            query.message.reply_text(text=text,
                                     parse_mode=ParseMode.MARKDOWN,
                                     reply_markup=InlineKeyboardMarkup(
                                         [[InlineKeyboardButton(text=tld(chat.id, "Back"), callback_data="help_back")]]))

        elif prev_match:
            curr_page = int(prev_match.group(1))
            query.message.reply_text(tld(chat.id, "send-help").format(dispatcher.bot.first_name, "" if not ALLOW_EXCL else tld(chat.id, "\nAll commands can either be used with `/` or `!`.\n")),
                                     parse_mode=ParseMode.MARKDOWN,
                                     reply_markup=InlineKeyboardMarkup(
                                         paginate_modules(chat.id, curr_page - 1, HELPABLE, "help")))

        elif next_match:
            next_page = int(next_match.group(1))
            query.message.reply_text(tld(chat.id, "send-help").format(dispatcher.bot.first_name, "" if not ALLOW_EXCL else tld(chat.id, "\nAll commands can either be used with `/` or `!`.\n")),
                                     parse_mode=ParseMode.MARKDOWN,
                                     reply_markup=InlineKeyboardMarkup(
                                         paginate_modules(chat.id, next_page + 1, HELPABLE, "help")))

        elif back_match:
            query.message.reply_text(text=tld(chat.id, "send-help").format(dispatcher.bot.first_name, "" if not ALLOW_EXCL else tld(chat.id, "\nAll commands can either be used with `/` or `!`.\n")),
                                     parse_mode=ParseMode.MARKDOWN,
                                     reply_markup=InlineKeyboardMarkup(
                                         paginate_modules(chat.id, 0, HELPABLE, "help")))



        # ensure no spinny white circle
        bot.answer_callback_query(query.id)
        query.message.delete()
    except BadRequest as excp:
        if excp.message == "Message is not modified":
            pass
        elif excp.message == "Query_id_invalid":
            pass
        elif excp.message == "Message can't be deleted":
            pass
        else:
            LOGGER.exception("Exception in help buttons. %s", str(query.data))


@run_async
def get_help(bot: Bot, update: Update):
    chat = update.effective_chat  # type: Optional[Chat]
    args = update.effective_message.text.split(None, 1)

    # ONLY send help in PM
    if chat.type != chat.PRIVATE:

        update.effective_message.reply_text("Contact me in PM to get the list of possible commands.",
                                            reply_markup=InlineKeyboardMarkup(
                                                [[InlineKeyboardButton(text="Help",
                                                                       url="t.me/{}?start=help".format(
                                                                           bot.username))]]))
        return

    elif len(args) >= 2 and any(args[1].lower() == x for x in HELPABLE):
        module = args[1].lower()
        mod_name = tld(chat.id, HELPABLE[module].__mod_name__)
        help_txt = tld_help(chat.id, HELPABLE[module].__mod_name__)

        if help_txt == False:
            help_txt = HELPABLE[module].__help__

        text = tld(chat.id, "Here is the help for the *{}* module:\n{}").format(mod_name, help_txt)
        send_help(chat.id, text, InlineKeyboardMarkup([[InlineKeyboardButton(text=tld(chat.id, "Back"), callback_data="help_back")]]))

    else:
        send_help(chat.id, tld(chat.id, "send-help").format(dispatcher.bot.first_name, "" if not ALLOW_EXCL else tld(
            chat.id, "\nAll commands can either be used with `/` or `!`.\n"
                )))

def send_settings(chat_id, user_id, user=False):
    if user:
        if USER_SETTINGS:
            settings = "\n\n".join(
                "*{}*:\n{}".format(mod.__mod_name__, mod.__user_settings__(user_id)) for mod in USER_SETTINGS.values())
            dispatcher.bot.send_message(user_id, "These are your current settings:" + "\n\n" + settings,
                                        parse_mode=ParseMode.MARKDOWN)

        else:
            dispatcher.bot.send_message(user_id, "Seems like there aren't any user specific settings available :'(",
                                        parse_mode=ParseMode.MARKDOWN)

    else:
        if CHAT_SETTINGS:
            chat_name = dispatcher.bot.getChat(chat_id).title
            dispatcher.bot.send_message(user_id,
                                        text="Which module would you like to check {}'s settings for?".format(
                                            chat_name),
                                        reply_markup=InlineKeyboardMarkup(
                                            paginate_modules(user_id, 0, CHAT_SETTINGS, "stngs", chat=chat_id)))
        else:
            dispatcher.bot.send_message(user_id, "Seems like there aren't any chat settings available :'(\nSend this "
                                                 "in a group chat you're admin in to find its current settings!",
                                        parse_mode=ParseMode.MARKDOWN)

