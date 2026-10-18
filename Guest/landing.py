"""
landing.py - Main window and navigation for Moxie.

Owns the QStackedWidget of pages (guest home, register, login, volunteer
home, FAQ, volunteer listing, org dashboard) plus the session-aware nav
bar, the guest search bar, and the global mic button.
"""

import webbrowser

from PyQt6.QtCore import Qt, QSettings, QTimer
from PyQt6.QtGui import QAction, QIcon, QPixmap, QCursor
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QMenu, QStackedWidget, QScrollArea,
    QMessageBox,
)

import Events.theme as theme
from db import Database
from Events.searchBar import SearchBar
from Guest.featuresSection import FeaturesSection
from Guest.heroSection import HeroSection
from Guest.opportunitiesSection import OpportunitiesSection
from Volunteer.volunteerRegister import VolunteerRegistration
from Organization.orgRegister import OrganizationRegistration
from Authentication.login import Login
from Volunteer.volunteerHome import VolunteerHome, TAB_PROFILE
from Guest.FAQ import FAQPage
from Volunteer.volunteerPage import VolunteerPage
from Organization.orgDashboard import OrgDashboard
from Guest.globalMic import GlobalMicButton


# Stack page indices
PAGE_HOME = 0
PAGE_VOL_REG = 1
PAGE_ORG_REG = 2
PAGE_LOGIN = 3
PAGE_VOL_HOME = 4
PAGE_FAQ = 5
PAGE_VOL_LIST = 6
PAGE_ORG_DASH = 7

# Nav modes
NAV_GUEST, NAV_VOLUNTEER, NAV_ORG = "guest", "volunteer", "org"


VOLUNTEER_NAV_GROUPS = [
    ("Home",        [("Dashboard", "vol_tab", 0),
                     ("Notifications", "vol_tab", 4)]),
    ("Discover",    [("Browse Events", "vol_list", None),
                     ("Volunteer Match", "vol_match", None),
                     ("Bookmarks", "vol_tab", 7)]),
    ("My Activity", [("Calendar", "vol_tab", 1),
                     ("My Events", "vol_tab", 2),
                     ("Organizations", "vol_tab", 3)]),
    ("Support",     [("Help", "vol_tab", 5),
                     ("FAQ", "show_faq", None)]),
    ("Account",     [("Profile", "vol_tab", 6),
                     ("Export my data", "open_export", None),
                     ("Log out", "handle_logout", None)]),
]

# NOTE: nav_idx 6 routes via NAV_TO_STACK[6] = TAB_RECOMMENDATIONS.
# Label was previously "Check-in codes" (wrong); now "Recommendations".
ORG_NAV_GROUPS = [
    ("Home",          [("Overview", "org_nav", 0),
                       ("Announcements", "org_nav", 4)]),
    ("Opportunities", [("My opportunities", "org_nav", 1),
                       ("Recommendations", "org_nav", 6)]),
    ("People",        [("Volunteers", "org_nav", 2),
                       ("Reports", "org_nav", 3)]),
    ("Data",          [("Data migration", "org_nav", 5)]),
    ("Account",       [("Help", "show_faq", None),
                       ("Log out", "handle_org_logout", None)]),
]

GUEST_NAV_GROUPS = [
    ("Discover",   [("Browse Volunteer Events", "vol_list", None),
                    ("Volunteer Match", "vol_match", None)]),
    ("Learn",      [("FAQ", "show_faq", None)]),
    ("Account",    [("Login", "show_login", None),
                    ("Register as Volunteer",
                     "show_vol_register", None),
                    ("Register an Organization",
                     "show_org_register", None)]),
    ("Appearance", [("Toggle dark / light mode", "toggle_theme", None)]),
]


class Landing(QMainWindow):
    def __init__(self, settings: QSettings | None = None):
        super().__init__()
        self.settings = settings or QSettings()

        self.setWindowTitle("Moxie")
        self.setWindowIcon(QIcon(theme.asset("logoHalfDark.png")))
        self.resize(1000, 700)

        self.is_dark_mode = (
            self.settings.value("theme", "light", type=str) == "dark"
        )

        self.current_user = None
        self.current_org = None
        self.matchPage = None

        self.nav_mode = NAV_GUEST
        self._nav_buttons = {}

        self.db = Database()

        self._build_ui()
        self.global_mic = GlobalMicButton(self)
        self.global_mic.reposition()
        self.global_mic.setVisible(False)
        self._wire_signals()
        self._set_nav_mode(NAV_GUEST)

        theme.apply_theme(self._app(), self.is_dark_mode)
        self._update_logos()
        self._sync_search_bar_visibility()
        self._refresh_home_carousels()

        # ── Notification badge polling (every 30s) ─────────────────
        self._notif_timer = QTimer(self)
        self._notif_timer.setInterval(30_000)
        self._notif_timer.timeout.connect(self._refresh_notif_badge)
        self._notif_timer.start()
        self._refresh_notif_badge()

    # ── UI construction ───────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_nav(), 0)

        self.searchBar = SearchBar()
        try:
            self.searchBar.populate_categories(
                self.db.getDistinctCategories()
            )
        except Exception as e:
            print("Could not load categories:", e)
        layout.addWidget(self.searchBar, 0)

        self.pageStack = QStackedWidget()
        self._populate_page_stack()
        layout.addWidget(self.pageStack, 1)

    def _build_nav(self):
        nav = QWidget()
        nav.setObjectName(theme.navBar)
        h = QHBoxLayout(nav)
        h.setContentsMargins(36, 18, 36, 18)
        h.setSpacing(12)

        self.nav_logo = QLabel()
        self.nav_logo.setObjectName(theme.navLogo)
        self.nav_logo.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self.nav_logo.mousePressEvent = lambda e: self.show_home_page()

        self.navTabs = QWidget()
        self.navTabsLayout = QHBoxLayout(self.navTabs)
        self.navTabsLayout.setContentsMargins(0, 0, 0, 0)
        self.navTabsLayout.setSpacing(4)

        self.btnThemeToggle = QPushButton(
            "\u263E\uFE0E" if not self.is_dark_mode else "\u2600\uFE0E"
        )
        self.btnThemeToggle.setObjectName(theme.NAV_GROUP_BTN)
        self.btnThemeToggle.setToolTip(
            "Switch to dark mode" if not self.is_dark_mode
            else "Switch to light mode"
        )
        self.btnThemeToggle.setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor)
        )
        self.btnThemeToggle.clicked.connect(self.toggle_theme)

        # NEW: unread-notification badge
        self.notif_badge = QLabel("0")
        self.notif_badge.setStyleSheet(
            "background:#C62828; color:white; border-radius:9px;"
            " font-size:10px; font-weight:bold; padding:2px 6px;"
        )
        self.notif_badge.setVisible(False)

        h.addWidget(self.nav_logo)
        h.addStretch()
        h.addWidget(self.navTabs)
        h.addWidget(self.notif_badge)   # NEW
        h.addWidget(self.btnThemeToggle)
        return nav

    def _populate_page_stack(self):
        # 0 - Guest home
        self.guestHomePage = self._build_guest_home()
        self.pageStack.addWidget(self.guestHomePage)

        # 1 - Volunteer register
        self.volunteerRegisterPage = VolunteerRegistration(
            db=self.db,
            on_success=self._handle_registration_success,
            on_back_click=self.show_home_page,
        )
        self.pageStack.addWidget(self.volunteerRegisterPage)

        # 2 - Org register
        self.orgRegisterPage = OrganizationRegistration(
            db=self.db,
            on_success=self._handle_registration_success,
            on_back_click=self.show_home_page,
        )
        self.pageStack.addWidget(self.orgRegisterPage)

        # 3 - Login
        self.loginPage = Login(
            db=self.db,
            on_login_success=self._handle_login_success,
            on_back_click=self.show_home_page,
        )
        self.pageStack.addWidget(self.loginPage)

        # 4 - Volunteer home
        self.volunteerHomePage = VolunteerHome(db=self.db)
        self.volunteerHomePage.tabChanged.connect(
            lambda _i: self._sync_nav_highlight()
        )
        self.volunteerHomePage.browseOpportunitiesRequested.connect(
            self.show_volunteer_listing_page
        )
        self.volunteerHomePage.goToProfileRequested.connect(
            lambda: self.show_volunteer_tab(TAB_PROFILE)
        )
        self.pageStack.addWidget(self.volunteerHomePage)

        # 5 - FAQ
        self.faqPage = FAQPage(on_back_click=self.show_home_page)
        self.pageStack.addWidget(self.faqPage)

        # 6 - Volunteer listing
        self.volunteerListingPage = VolunteerPage(
            db=self.db, on_back_click=self.show_home_page
        )
        self.volunteerListingPage.openLinkRequested.connect(
            self.open_external_link
        )
        self.volunteerListingPage.rsvpSucceeded.connect(
            self._handle_rsvp_success
        )
        self.pageStack.addWidget(self.volunteerListingPage)

        # 7 - Org dashboard
        self.orgDashboard = OrgDashboard(
            db=self.db,
            on_logout_click=self.handle_org_logout,
            on_back_click=self.show_home_page,
        )
        if hasattr(self.orgDashboard, "tabChanged"):
            self.orgDashboard.tabChanged.connect(
                lambda _i: self._sync_nav_highlight()
            )
        self.pageStack.addWidget(self.orgDashboard)

    def _build_guest_home(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.homeScrollArea = QScrollArea()
        self.homeScrollArea.setObjectName(theme.HOME_SCROLL)
        self.homeScrollArea.setWidgetResizable(True)
        self.homeScrollArea.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.homeScrollArea.setFrameShape(QScrollArea.Shape.NoFrame)

        content = QWidget()
        content.setObjectName(theme.HOME_SCROLL_CONTENT)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.hero_widget = self._build_hero()
        layout.addWidget(self.hero_widget, 0)

        self.featuresSection = FeaturesSection()
        self.featuresSection.discoverRequested.connect(
            lambda: self.show_volunteer_listing_page()
        )
        self.featuresSection.postRequested.connect(
            self.show_org_register_page
        )
        self.featuresSection.manageRequested.connect(
            self.show_org_register_page
        )
        layout.addWidget(self.featuresSection)

        self.opportunitiesSection = OpportunitiesSection()
        self.opportunitiesSection.detailsRequested.connect(
            self._open_event_details
        )
        self.opportunitiesSection.openLinkRequested.connect(
            self.open_external_link
        )
        self.opportunitiesSection.rsvpRequested.connect(
            self._handle_home_rsvp
        )
        layout.addWidget(self.opportunitiesSection)
        layout.addStretch(1)

        self.homeScrollArea.setWidget(content)
        outer.addWidget(self.homeScrollArea)
        return page

    def _build_hero(self):
        hero = HeroSection()
        hero.learnMoreRequested.connect(self.show_volunteer_listing_page)
        return hero

    # ── Session-aware nav bar (grouped) ───────────────────────────
    def _set_nav_mode(self, mode):
        self.nav_mode = mode

        while self.navTabsLayout.count():
            item = self.navTabsLayout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._nav_buttons = {}

        if mode == NAV_VOLUNTEER:
            groups = VOLUNTEER_NAV_GROUPS
        elif mode == NAV_ORG:
            groups = ORG_NAV_GROUPS
        else:
            groups = GUEST_NAV_GROUPS

        for group_label, items in groups:
            btn = QPushButton(f"{group_label}  ▾")
            btn.setObjectName(theme.NAV_GROUP_BTN)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            menu = QMenu(btn)
            for label, action, arg in items:
                a = QAction(label, self)
                a.triggered.connect(
                    lambda _c=False, act=action, a_arg=arg:
                    self._dispatch_nav(act, a_arg)
                )
                menu.addAction(a)
            btn.setMenu(menu)
            self.navTabsLayout.addWidget(btn)

    def _dispatch_nav(self, action, arg):
        if action == "vol_tab":
            self.show_volunteer_tab(arg)
        elif action == "vol_list":
            self.show_volunteer_listing_page()
        elif action == "vol_match":
            self.show_volunteer_match_page()
        elif action == "org_nav":
            self._show_org_nav_tab(arg)
        elif action == "show_faq":
            self.show_faq_page()
        elif action == "open_export":
            self._open_export_dialog()
        elif action == "handle_logout":
            self.handle_logout()
        elif action == "handle_org_logout":
            self.handle_org_logout()
        elif action == "toggle_theme":
            self.toggle_theme()
        elif action == "show_login":
            self.show_login_page()
        elif action == "show_vol_register":
            self.show_volunteer_register_page()
        elif action == "show_org_register":
            self.show_org_register_page()

    def _active_nav_key(self):
        return None

    def _sync_nav_highlight(self):
        return

    # ── Signals ───────────────────────────────────────────────────
    def _wire_signals(self):
        self.searchBar.searchRequested.connect(self.handle_search)

    # ── Navigation helpers ────────────────────────────────────────
    def _goto(self, page_widget):
        self.pageStack.setCurrentWidget(page_widget)
        self._sync_search_bar_visibility()
        self._sync_nav_highlight()

    def _sync_search_bar_visibility(self):
        self.searchBar.setVisible(
            self.pageStack.currentWidget() is self.guestHomePage
        )

    def show_home_page(self):
        if self.current_user:
            self._goto(self.volunteerHomePage)
        elif self.current_org:
            self._goto(self.orgDashboard)
        else:
            self._goto(self.guestHomePage)

    def show_volunteer_tab(self, idx):
        self._goto(self.volunteerHomePage)
        self.volunteerHomePage.show_tab(idx)
        # Opening the notifications tab should clear the badge count
        # on the next poll; volunteerNotifications marks them read.
        if idx == 4:
            self._refresh_notif_badge()

    def show_org_tab(self, idx):
        self._goto(self.orgDashboard)
        show = getattr(self.orgDashboard, "show_tab", None)
        if callable(show):
            show(idx)

    def _show_org_nav_tab(self, nav_idx):
        self._goto(self.orgDashboard)
        fn = getattr(self.orgDashboard, "show_nav_tab", None)
        if callable(fn):
            fn(nav_idx)
        else:
            show = getattr(self.orgDashboard, "show_tab", None)
            if callable(show):
                show(nav_idx)

    def show_volunteer_listing_page(self, keyword=None, filters=None):
        if keyword:
            self.volunteerListingPage.set_search_text(keyword)
        if filters:
            self.volunteerListingPage.apply_external_filters(filters)
        self._goto(self.volunteerListingPage)

    def show_volunteer_register_page(self):
        self._goto(self.volunteerRegisterPage)

    def show_org_register_page(self):
        self._goto(self.orgRegisterPage)

    def show_faq_page(self):
        self._goto(self.faqPage)

    def show_login_page(self):
        self.loginPage.clear_inputs()
        self._goto(self.loginPage)

    def handle_login_nav_click(self):
        if self.current_user:
            self.handle_logout()
        elif self.current_org:
            self.handle_org_logout()
        else:
            self.show_login_page()

    # ── Volunteer Match ───────────────────────────────────────────
    def show_volunteer_match_page(self):
        if not self.current_user:
            QMessageBox.information(
                self, "Login required",
                "Log in as a volunteer to use Volunteer Match.",
            )
            return
        if self.matchPage is None:
            from Volunteer.volunteerMatch import VolunteerMatch
            self.matchPage = VolunteerMatch(self.db)
            self.matchPage.browseAllRequested.connect(
                self.show_volunteer_listing_page
            )
            self.pageStack.addWidget(self.matchPage)
        self.matchPage.set_volunteer(self.current_user["userID"])
        self._goto(self.matchPage)

    # ── Export dialog ─────────────────────────────────────────────
    def _open_export_dialog(self):
        if not self.current_user:
            return
        from Volunteer.exportDialog import ExportDialog
        ExportDialog(self.db, self.current_user["userID"], self).exec()

    # ── Registration callback ─────────────────────────────────────
    def _handle_registration_success(self, userID):
        self.show_login_page()

    # ── Login callback ────────────────────────────────────────────
    def _handle_login_success(self, user):
        if user["role"] == "volunteer":
            self.current_user = user
            self.current_org = None
            self._set_nav_mode(NAV_VOLUNTEER)
            self.volunteerHomePage.set_user_data(user)
            self.volunteerListingPage.set_current_volunteer(user["userID"])
            self._refresh_home_carousels()
            self._goto(self.volunteerHomePage)
        else:
            self.current_org = user
            self.current_user = None
            self._set_nav_mode(NAV_ORG)
            self.orgDashboard.set_org_data(user)
            self._goto(self.orgDashboard)
        self._refresh_notif_badge()

    # ── Logout callbacks ──────────────────────────────────────────
    def handle_logout(self):
        self.current_user = None
        self.volunteerListingPage.set_current_volunteer(None)
        self._set_nav_mode(NAV_GUEST)
        self._refresh_home_carousels()
        self._goto(self.guestHomePage)
        self._refresh_notif_badge()

    def handle_org_logout(self):
        self.current_org = None
        self._set_nav_mode(NAV_GUEST)
        self._goto(self.guestHomePage)
        self._refresh_notif_badge()

    # ── RSVP callbacks ────────────────────────────────────────────
    def _handle_rsvp_success(self, opportunity_id):
        if not self.current_user:
            return
        self._goto(self.volunteerHomePage)
        self.volunteerHomePage.show_my_events()

    def _handle_home_rsvp(self, opportunity_id):
        if not self.current_user:
            QMessageBox.information(
                self, "Login required",
                "Log in as a volunteer to sign up for events.",
            )
            return

        result = self.db.registerForOpportunity(
            self.current_user["userID"], opportunity_id
        )
        if result == "ok":
            try:
                row = self.db.getOpportunityByID(opportunity_id)
                title = row["title"] if row else "an event"
                self.db.addNotification(
                    self.current_user["userID"],
                    f"You signed up for {title}.",
                    "rsvp", opportunity_id,
                )
            except Exception as e:
                print("addNotification failed:", e)
            QMessageBox.information(
                self, "Registered",
                "You're signed up! Taking you to My Events.",
            )
            self._handle_rsvp_success(opportunity_id)
        elif result == "duplicate":
            QMessageBox.information(
                self, "Already registered",
                "You've already RSVP'd for this event.",
            )
        elif result == "full":
            QMessageBox.warning(
                self, "Event full",
                "This event has reached capacity.",
            )
        else:
            QMessageBox.warning(self, "Error", "Could not complete RSVP.")

    def _open_event_details(self, card):
        from Events.eventDetailsDialog import EventDetailsDialog
        EventDetailsDialog(card, self).exec()

    # ── Home carousels ────────────────────────────────────────────
    def _refresh_home_carousels(self):
        if not hasattr(self, "opportunitiesSection"):
            return
        volunteer_id = (self.current_user["userID"]
                        if self.current_user else None)
        try:
            self.opportunitiesSection.load_from_db(
                self.db, current_volunteer_id=volunteer_id
            )
        except Exception as e:
            print("Failed to refresh home carousels:", e)

    # ── Search ────────────────────────────────────────────────────
    def handle_search(self, filters: dict):
        if not filters:
            return
        self.show_volunteer_listing_page(filters=filters)

    def open_external_link(self, url):
        if url:
            webbrowser.open(url)

    # ── Theme ─────────────────────────────────────────────────────
    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.settings.setValue(
            "theme", "dark" if self.is_dark_mode else "light"
        )
        theme.apply_theme(self._app(), self.is_dark_mode)
        self.btnThemeToggle.setText(
            "\u2600\uFE0E" if self.is_dark_mode else "\u263E\uFE0E"
        )
        self.btnThemeToggle.setToolTip(
            "Switch to light mode" if self.is_dark_mode
            else "Switch to dark mode"
        )
        self._update_logos()

    def _update_logos(self):
        filename = ("logoFullLight.png" if self.is_dark_mode
                    else "logoFullDark.png")
        path = theme.asset(filename)

        smooth = Qt.TransformationMode.SmoothTransformation
        nav_pixmap = QPixmap(path).scaledToHeight(46, smooth)
        self.nav_logo.setPixmap(nav_pixmap)

        if (hasattr(self, "hero_widget")
                and hasattr(self.hero_widget, "set_theme")):
            self.hero_widget.set_theme(self.is_dark_mode)

    # ── Notification badge ────────────────────────────────────────
    def _refresh_notif_badge(self):
        """Poll the DB and update the badge with the unread count.

        Badge only shows for volunteers. `read_at` is populated when the
        notifications tab is opened (see volunteerNotifications.py)."""
        if not self.current_user:
            self.notif_badge.setVisible(False)
            return
        try:
            rows = self.db.getNotifications(
                self.current_user["userID"], limit=50
            ) or []
        except Exception:
            return
        unread = sum(1 for r in rows if not r["read_at"])
        if unread:
            self.notif_badge.setText(str(unread))
            self.notif_badge.setVisible(True)
        else:
            self.notif_badge.setVisible(False)

    # ── Hero sizing ───────────────────────────────────────────────
    def _sync_hero_height(self):
        return

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "global_mic"):
            self.global_mic.reposition()
            self.global_mic.raise_()

    # ── Utilities ─────────────────────────────────────────────────
    def _app(self):
        return QApplication.instance()

    def closeEvent(self, event):
        try:
            self.db.close()
        except Exception:
            pass
        super().closeEvent(event)