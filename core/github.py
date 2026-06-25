"""GitHub module for TerminalX EcoSystem.

polsoft.ITS(TM) Group  *  Sebastian Januchowski
Module: github  v1.0.0

Integracja z GitHub API — logowanie przez Personal Access Token,
przeglądanie repozytoriów, issues, profilu i gistów.
Token jest przechowywany w .cache/global/github_auth.json (chmod 600).

Komendy:
  github                   - status konta / pomoc
  github login <token>     - zaloguj się tokenem PAT
  github logout            - usuń zapisany token
  github whoami            - pokaż zalogowanego użytkownika
  github repos [user]      - lista repozytoriów (własnych lub <user>)
  github issues <owner/repo> - lista otwartych issues
  github gists [user]      - lista gistów
  github star <owner/repo> - dodaj gwiazdkę
  github unstar <owner/repo> - usuń gwiazdkę
  github info <owner/repo> - szczegóły repozytorium
"""

import json
import os
import stat
import urllib.request
import urllib.error
import urllib.parse

from ._shared import CACHE_DIR, RST, BOLD, DIM, YLW, RED, GRN, CYN, WHT, MGT, _w, _atomic_write

_VERSION = "1.0.0"
_AUTH_FILE = os.path.join(CACHE_DIR, "global", "github_auth.json")
_API_BASE  = "https://api.github.com"


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _load_token() -> str | None:
    """Wczytaj zapisany PAT z cache."""
    try:
        with open(_AUTH_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("token") or None
    except Exception:
        return None


def _save_token(token: str) -> bool:
    """Zapisz token do cache (uprawnienia 600 na POSIX)."""
    try:
        os.makedirs(os.path.dirname(_AUTH_FILE), exist_ok=True)
    except OSError:
        return False

    ok = _atomic_write(_AUTH_FILE, {"token": token})
    if ok:
        try:
            os.chmod(_AUTH_FILE, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    return ok


def _delete_token() -> bool:
    """Usuń plik z tokenem."""
    try:
        os.remove(_AUTH_FILE)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# GitHub API helper
# ---------------------------------------------------------------------------

def _api(path: str, token: str | None = None, method: str = "GET",
         body: dict | None = None) -> tuple[int, dict | list | None]:
    """Wykonaj żądanie do GitHub API.

    Zwraca (status_code, data).  data == None gdy brak ciała (np. 204).
    Rzuca urllib.error.URLError / urllib.error.HTTPError przy błędzie sieci.
    """
    url = f"{_API_BASE}{path}"
    headers = {
        "Accept":     "application/vnd.github+json",
        "User-Agent": "TerminalX-polsoft/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data_bytes = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            code = resp.status
            raw  = resp.read()
            return code, json.loads(raw) if raw.strip() else None
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"message": exc.reason}
        return exc.code, payload


# ---------------------------------------------------------------------------
# Formatowanie
# ---------------------------------------------------------------------------

def _fmt_repo(r: dict, idx: int | None = None) -> str:
    """Sformatuj jeden rekord repozytorium."""
    name    = r.get("full_name", r.get("name", "?"))
    desc    = r.get("description") or ""
    stars   = r.get("stargazers_count", 0)
    forks   = r.get("forks_count", 0)
    lang    = r.get("language") or "-"
    private = r.get("private", False)
    vis     = f"{RED}[prywatne]{RST}" if private else f"{DIM}[publiczne]{RST}"

    prefix = f"  {DIM}{idx:>3}.{RST} " if idx is not None else "  "
    line1  = f"{prefix}{BOLD}{CYN}{name}{RST}  {vis}"
    line2  = f"       {DIM}{desc[:70]}{RST}" if desc else ""
    line3  = f"       {YLW}★ {stars}{RST}  {DIM}⑂ {forks}{RST}  {WHT}{lang}{RST}"
    return "\n".join(filter(None, [line1, line2, line3]))


def _fmt_issue(i: dict, idx: int) -> str:
    num   = i.get("number", "?")
    title = i.get("title", "?")
    user  = i.get("user", {}).get("login", "?")
    state = i.get("state", "?")
    col   = GRN if state == "open" else RED
    labels = ", ".join(lb["name"] for lb in i.get("labels", []))
    line1 = f"  {DIM}{idx:>3}.{RST}  {col}#{num}{RST}  {BOLD}{title[:65]}{RST}"
    line2 = f"        {DIM}autor: {user}  etykiety: {labels or '-'}{RST}"
    return line1 + "\n" + line2


def _fmt_gist(g: dict, idx: int) -> str:
    desc  = g.get("description") or "(bez opisu)"
    files = ", ".join(list(g.get("files", {}).keys())[:3])
    pub   = f"{GRN}publiczny{RST}" if g.get("public") else f"{DIM}prywatny{RST}"
    line1 = f"  {DIM}{idx:>3}.{RST}  {BOLD}{desc[:60]}{RST}  {pub}"
    line2 = f"        {DIM}{files}{RST}"
    return line1 + "\n" + line2


# ---------------------------------------------------------------------------
# Podkomendy
# ---------------------------------------------------------------------------

def _cmd_login(args: list, _t) -> None:
    if not args:
        _w(f"\n  {RED}{_t('gh_login_usage')}{RST}\n\n")
        return

    token = args[0].strip()
    if not token.startswith(("ghp_", "github_pat_", "gho_", "ghu_", "ghs_", "ghr_")):
        _w(f"\n  {YLW}{_t('gh_token_format_warn')}{RST}\n")

    _w(f"  {DIM}{_t('gh_verifying')}...{RST}\n")
    try:
        code, data = _api("/user", token=token)
    except Exception as exc:
        _w(f"\n  {RED}{_t('gh_net_error', exc=exc)}{RST}\n\n")
        return

    if code != 200:
        msg = data.get("message", str(code)) if isinstance(data, dict) else str(code)
        _w(f"\n  {RED}{_t('gh_auth_fail', msg=msg)}{RST}\n\n")
        return

    login = data.get("login", "?")
    name  = data.get("name") or login
    if not _save_token(token):
        _w(f"\n  {RED}{_t('gh_save_fail')}{RST}\n\n")
        return

    _w(f"\n  {GRN}{_t('gh_logged_in', login=login, name=name)}{RST}\n\n")


def _cmd_logout(args: list, _t) -> None:
    if _delete_token():
        _w(f"\n  {GRN}{_t('gh_logged_out')}{RST}\n\n")
    else:
        _w(f"\n  {RED}{_t('gh_logout_fail')}{RST}\n\n")


def _cmd_whoami(args: list, _t) -> None:
    token = _load_token()
    if not token:
        _w(f"\n  {YLW}{_t('gh_not_logged')}{RST}\n\n")
        return
    try:
        code, data = _api("/user", token=token)
    except Exception as exc:
        _w(f"\n  {RED}{_t('gh_net_error', exc=exc)}{RST}\n\n")
        return
    if code != 200 or not isinstance(data, dict):
        _w(f"\n  {RED}{_t('gh_api_error', code=code)}{RST}\n\n")
        return

    login  = data.get("login", "?")
    name   = data.get("name") or "-"
    email  = data.get("email") or "-"
    bio    = data.get("bio") or "-"
    repos  = data.get("public_repos", 0)
    follow = data.get("followers", 0)
    plan   = (data.get("plan") or {}).get("name", "-")

    _w(f"\n  {BOLD}{CYN}@{login}{RST}  {DIM}({name}){RST}\n")
    _w(f"  {DIM}e-mail : {RST}{email}\n")
    _w(f"  {DIM}bio    : {RST}{bio[:70]}\n")
    _w(f"  {DIM}repoz. : {RST}{YLW}{repos}{RST}   "
       f"{DIM}obserwujący: {RST}{YLW}{follow}{RST}   "
       f"{DIM}plan: {RST}{YLW}{plan}{RST}\n\n")


def _cmd_repos(args: list, _t) -> None:
    token = _load_token()
    if args:
        # repos innego usera — nie wymaga tokena
        user = args[0]
        path = f"/users/{urllib.parse.quote(user)}/repos?per_page=30&sort=updated"
    else:
        if not token:
            _w(f"\n  {YLW}{_t('gh_not_logged')}{RST}\n\n")
            return
        path = "/user/repos?per_page=30&sort=updated&affiliation=owner"

    try:
        code, data = _api(path, token=token)
    except Exception as exc:
        _w(f"\n  {RED}{_t('gh_net_error', exc=exc)}{RST}\n\n")
        return
    if code != 200 or not isinstance(data, list):
        msg = data.get("message", str(code)) if isinstance(data, dict) else str(code)
        _w(f"\n  {RED}{_t('gh_api_error', code=code)} — {msg}{RST}\n\n")
        return
    if not data:
        _w(f"\n  {DIM}{_t('gh_no_repos')}{RST}\n\n")
        return

    label = args[0] if args else _t("gh_your_repos")
    _w(f"\n  {BOLD}{CYN}{_t('gh_repos_header', label=label)}  ({len(data)}){RST}\n\n")
    for i, r in enumerate(data, 1):
        _w(_fmt_repo(r, i) + "\n\n")


def _cmd_issues(args: list, _t) -> None:
    token = _load_token()
    if not args:
        _w(f"\n  {RED}{_t('gh_issues_usage')}{RST}\n\n")
        return
    repo = args[0]
    path = f"/repos/{repo}/issues?state=open&per_page=30"
    try:
        code, data = _api(path, token=token)
    except Exception as exc:
        _w(f"\n  {RED}{_t('gh_net_error', exc=exc)}{RST}\n\n")
        return
    if code != 200 or not isinstance(data, list):
        msg = data.get("message", str(code)) if isinstance(data, dict) else str(code)
        _w(f"\n  {RED}{_t('gh_api_error', code=code)} — {msg}{RST}\n\n")
        return
    # odfiltruj pull requesty (mają klucz pull_request)
    issues = [i for i in data if "pull_request" not in i]
    if not issues:
        _w(f"\n  {DIM}{_t('gh_no_issues')}{RST}\n\n")
        return
    _w(f"\n  {BOLD}{CYN}{_t('gh_issues_header', repo=repo)}  ({len(issues)}){RST}\n\n")
    for idx, issue in enumerate(issues, 1):
        _w(_fmt_issue(issue, idx) + "\n\n")


def _cmd_gists(args: list, _t) -> None:
    token = _load_token()
    if args:
        user = args[0]
        path = f"/users/{urllib.parse.quote(user)}/gists?per_page=20"
    else:
        if not token:
            _w(f"\n  {YLW}{_t('gh_not_logged')}{RST}\n\n")
            return
        path = "/gists?per_page=20"
    try:
        code, data = _api(path, token=token)
    except Exception as exc:
        _w(f"\n  {RED}{_t('gh_net_error', exc=exc)}{RST}\n\n")
        return
    if code != 200 or not isinstance(data, list):
        msg = data.get("message", str(code)) if isinstance(data, dict) else str(code)
        _w(f"\n  {RED}{_t('gh_api_error', code=code)} — {msg}{RST}\n\n")
        return
    if not data:
        _w(f"\n  {DIM}{_t('gh_no_gists')}{RST}\n\n")
        return
    _w(f"\n  {BOLD}{CYN}{_t('gh_gists_header')}  ({len(data)}){RST}\n\n")
    for i, g in enumerate(data, 1):
        _w(_fmt_gist(g, i) + "\n\n")


def _cmd_star(args: list, _t, unstar: bool = False) -> None:
    token = _load_token()
    if not token:
        _w(f"\n  {YLW}{_t('gh_not_logged')}{RST}\n\n")
        return
    if not args:
        _w(f"\n  {RED}{_t('gh_star_usage')}{RST}\n\n")
        return
    repo   = args[0]
    method = "DELETE" if unstar else "PUT"
    path   = f"/user/starred/{repo}"
    try:
        code, _ = _api(path, token=token, method=method)
    except Exception as exc:
        _w(f"\n  {RED}{_t('gh_net_error', exc=exc)}{RST}\n\n")
        return
    if code in (204, 200):
        key = "gh_unstarred" if unstar else "gh_starred"
        _w(f"\n  {GRN}{_t(key, repo=repo)}{RST}\n\n")
    else:
        _w(f"\n  {RED}{_t('gh_api_error', code=code)}{RST}\n\n")


def _cmd_info(args: list, _t) -> None:
    token = _load_token()
    if not args:
        _w(f"\n  {RED}{_t('gh_info_usage')}{RST}\n\n")
        return
    repo = args[0]
    try:
        code, data = _api(f"/repos/{repo}", token=token)
    except Exception as exc:
        _w(f"\n  {RED}{_t('gh_net_error', exc=exc)}{RST}\n\n")
        return
    if code != 200 or not isinstance(data, dict):
        msg = data.get("message", str(code)) if isinstance(data, dict) else str(code)
        _w(f"\n  {RED}{_t('gh_api_error', code=code)} — {msg}{RST}\n\n")
        return

    name    = data.get("full_name", repo)
    desc    = data.get("description") or "-"
    stars   = data.get("stargazers_count", 0)
    forks   = data.get("forks_count", 0)
    issues  = data.get("open_issues_count", 0)
    lang    = data.get("language") or "-"
    lic     = (data.get("license") or {}).get("spdx_id", "-")
    size    = data.get("size", 0)
    default = data.get("default_branch", "-")
    url     = data.get("html_url", "-")
    topics  = ", ".join(data.get("topics", [])) or "-"
    private = data.get("private", False)
    vis     = f"{RED}prywatne{RST}" if private else f"{GRN}publiczne{RST}"

    _w(f"\n  {BOLD}{CYN}{name}{RST}  [{vis}]\n")
    _w(f"  {DIM}opis       : {RST}{desc[:80]}\n")
    _w(f"  {DIM}jezyk      : {RST}{lang}   {DIM}licencja: {RST}{lic}   {DIM}rozmiar: {RST}{size} KB\n")
    _w(f"  {DIM}★ gwiazdki : {RST}{YLW}{stars}{RST}   "
       f"{DIM}⑂ forki: {RST}{YLW}{forks}{RST}   "
       f"{DIM}issues: {RST}{YLW}{issues}{RST}\n")
    _w(f"  {DIM}gałąź     : {RST}{default}   {DIM}tematy: {RST}{topics[:60]}\n")
    _w(f"  {DIM}url        : {RST}{MGT}{url}{RST}\n\n")


def _show_help(_t) -> None:
    token  = _load_token()
    status = f"{GRN}{_t('gh_status_logged')}{RST}" if token else f"{YLW}{_t('gh_status_anon')}{RST}"

    _w(f"\n  {BOLD}{CYN}GitHub  v{_VERSION}{RST}  —  {status}\n\n")
    rows = [
        ("github login <token>",        _t("gh_help_login")),
        ("github logout",               _t("gh_help_logout")),
        ("github whoami",               _t("gh_help_whoami")),
        ("github repos [user]",         _t("gh_help_repos")),
        ("github issues <owner/repo>",  _t("gh_help_issues")),
        ("github gists [user]",         _t("gh_help_gists")),
        ("github star <owner/repo>",    _t("gh_help_star")),
        ("github unstar <owner/repo>",  _t("gh_help_unstar")),
        ("github info <owner/repo>",    _t("gh_help_info")),
    ]
    for cmd, desc in rows:
        _w(f"  {YLW}{cmd:<36}{RST}  {DIM}{desc}{RST}\n")
    _w(f"\n  {DIM}{_t('gh_token_hint')}{RST}\n\n")


# ---------------------------------------------------------------------------
# setup / teardown
# ---------------------------------------------------------------------------

def setup(terminal) -> None:

    # Rejestracja w _integration
    try:
        from . import _integration as _intg
        _intg.register("github", {
            "get_token": _load_token,
        })
    except Exception:
        pass

    _t = terminal.t

    _SUBS = {
        "login":  lambda a: _cmd_login(a, _t),
        "logout": lambda a: _cmd_logout(a, _t),
        "whoami": lambda a: _cmd_whoami(a, _t),
        "repos":  lambda a: _cmd_repos(a, _t),
        "issues": lambda a: _cmd_issues(a, _t),
        "gists":  lambda a: _cmd_gists(a, _t),
        "star":   lambda a: _cmd_star(a, _t, unstar=False),
        "unstar": lambda a: _cmd_star(a, _t, unstar=True),
        "info":   lambda a: _cmd_info(a, _t),
    }

    def github(args: list) -> None:
        if not args:
            _show_help(_t)
            return
        sub  = args[0].lower()
        rest = args[1:]
        fn   = _SUBS.get(sub)
        if fn is None:
            _w(f"\n  {RED}{_t('gh_unknown_sub', sub=sub)}{RST}\n\n")
            return
        fn(rest)

    terminal.register_command(
        "github", github,
        description=_t("cmd_github"),
        category=_t("cat_net"),
    )

    # Auto-weryfikacja tokena przy starcie (cicha — tylko przy błędzie 401)
    token = _load_token()
    if token:
        try:
            code, data = _api("/user", token=token)
            if code == 401:
                login_hint = _t("gh_token_expired")
                _w(f"  {YLW}[github] {login_hint}{RST}\n")
        except Exception:
            pass


def teardown(terminal) -> None:
    try:
        from . import _integration as _intg
        _intg.unregister("github")
    except Exception:
        pass
    terminal.commands.pop("github", None)
