"""
auth.py
-------
Streamlit authentication UI module for the Flight Price Monitor.

Provides:
  show_auth_page()   – renders Login / Register tabs and calls st.stop() if
                       the user is not authenticated. Call this at the very
                       top of app.py before any other UI.
  logout()           – clears session state (call from a sidebar button).
  current_user()     – returns the logged-in user dict, or None.

Session keys managed here:
  st.session_state["authenticated"]   bool
  st.session_state["user"]            dict  (UserId, Email, DisplayName)
"""

import re
import streamlit as st

from src.database.auth_store import create_user, verify_password


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_valid_email(email: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))


def _auth_css() -> None:
    """Inject card-style CSS for the auth page."""
    st.markdown("""
    <style>
      .auth-container {
        max-width: 420px;
        margin: 4rem auto;
        background: #2d2e31;
        border: 1px solid #3c4043;
        border-radius: 16px;
        padding: 2rem 2.5rem;
      }
      .auth-title {
        font-size: 1.6rem;
        font-weight: 800;
        color: #8ab4f8;
        margin-bottom: 0.25rem;
      }
      .auth-subtitle {
        color: #9aa0a6;
        font-size: 0.9rem;
        margin-bottom: 1.5rem;
      }
    </style>
    """, unsafe_allow_html=True)


def _login_form() -> None:
    """Render the login form. Sets session state on success."""
    st.markdown("#### Sign in to your account")

    with st.form("login_form", clear_on_submit=False):
        email    = st.text_input("Email address", placeholder="you@example.com")
        password = st.text_input("Password", type="password", placeholder="••••••••")
        submitted = st.form_submit_button("Sign in", use_container_width=True)

    if submitted:
        email = email.strip().lower()

        if not email or not password:
            st.error("Please enter both your email and password.")
            return

        if not _is_valid_email(email):
            st.error("Enter a valid email address.")
            return

        with st.spinner("Verifying credentials…"):
            ok, user = verify_password(email, password)

        if ok and user:
            st.session_state["authenticated"] = True
            st.session_state["user"] = {
                "UserId":      user["UserId"],
                "Email":       user["Email"],
                "DisplayName": user.get("DisplayName", email.split("@")[0]),
            }
            st.success(f"Welcome back, {st.session_state['user']['DisplayName']}! 👋")
            st.rerun()
        else:
            st.error("Incorrect email or password. Please try again.")


def _register_form() -> None:
    """Render the registration form. Creates account on success."""
    st.markdown("#### Create a new account")

    with st.form("register_form", clear_on_submit=True):
        display_name = st.text_input("Your name",       placeholder="Ada Lovelace")
        email        = st.text_input("Email address",   placeholder="you@example.com")
        password     = st.text_input("Password",        type="password",
                                     placeholder="At least 8 characters",
                                     help="Minimum 8 characters.")
        password2    = st.text_input("Confirm password", type="password",
                                     placeholder="Repeat your password")
        submitted = st.form_submit_button("Create account", use_container_width=True)

    if submitted:
        email = email.strip().lower()
        display_name = display_name.strip()

        # ── Validation ────────────────────────────────────────────────────────
        errors = []
        if not display_name:
            errors.append("Please enter your name.")
        if not _is_valid_email(email):
            errors.append("Enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != password2:
            errors.append("Passwords do not match.")

        if errors:
            for e in errors:
                st.error(e)
            return

        # ── Registration ──────────────────────────────────────────────────────
        with st.spinner("Creating your account…"):
            ok, msg = create_user(email, password, display_name)

        if ok:
            st.success("✅ Account created! You can now sign in.")
            st.balloons()
        else:
            st.error(msg)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def show_auth_page() -> None:
    """
    Gate the entire app behind authentication.

    Call this ONCE at the top of app.py, before any other UI code.
    If the user is not authenticated, this renders the auth page and
    calls st.stop() so the rest of the app never executes.
    """
    if st.session_state.get("authenticated"):
        return   # Already logged in — let the app continue

    _auth_css()

    # Centred logo + title
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.image(
            "https://www.gstatic.com/images/branding/product/2x/google_flights_64dp.png",
            width=56,
        )
        st.markdown(
            "<div class='auth-title'>✈️ Flight Price Monitor</div>"
            "<div class='auth-subtitle'>Serverless AWS price-drop alerts</div>",
            unsafe_allow_html=True,
        )

        login_tab, register_tab = st.tabs(["Sign in", "Create account"])

        with login_tab:
            _login_form()

        with register_tab:
            _register_form()

    st.stop()   # Nothing below this line runs until the user is authenticated


def logout() -> None:
    """
    Clear authentication state. Call from a sidebar button.

    Example:
        if st.sidebar.button("Sign out"):
            auth.logout()
    """
    for key in ("authenticated", "user", "trackers", "search_results", "search_meta"):
        st.session_state.pop(key, None)
    st.rerun()


def current_user() -> dict | None:
    """
    Return the currently logged-in user dict, or None if not authenticated.

    Dict shape: { "UserId": str, "Email": str, "DisplayName": str }
    """
    if st.session_state.get("authenticated"):
        return st.session_state.get("user")
    return None
