"""
Install Instructions.

How to get what the app needs onto a machine, per platform. Data rather than
behaviour, following the `templates.py` convention in CODE_STYLE.md — the same
pattern as `identifier/templates.py`, which holds the film vocabulary.

Lives apart from `environment.py` because checking whether something is
installed and explaining how to install it are different jobs. One of them is
read by the Setup tab whatever state the machine is in, which is the whole
point of having it: the checks only speak up when something is missing, and
that is useless to the person setting up a second machine.

**Every platform ends with a download that needs no package manager.** A single
command assumes a tool the user may not have — `brew install ffmpeg` on a Mac
without Homebrew fails with "command not found", which reads as the app being
broken rather than as a missing prerequisite. A test asserts this holds, so it
cannot quietly stop being true.

Each entry is `(label, command, url)`. Exactly one of command or url is set;
the label says what the option is for.
"""

# --- FFMPEG ---

FFMPEG_INSTALL = {
    "Windows": [
        ("With winget (Windows 10 and 11)", "winget install Gyan.FFmpeg", None),
        ("Or download a build", None, "https://www.gyan.dev/ffmpeg/builds/"),
    ],
    "Darwin": [
        ("With Homebrew", "brew install ffmpeg", None),
        (
            "No Homebrew? Install it first",
            '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"',
            None,
        ),
        ("Or download a build", None, "https://evermeet.cx/ffmpeg/"),
    ],
    "Linux": [
        ("Debian and Ubuntu", "sudo apt install ffmpeg", None),
        ("Fedora", "sudo dnf install ffmpeg", None),
        ("Or download a build", None, "https://johnvansickle.com/ffmpeg/"),
    ],
}

# Used where the platform is not one of the three above.
FFMPEG_FALLBACK = [
    ("Install ffmpeg and put it on PATH", None, "https://ffmpeg.org/download.html"),
]

# --- FFMPEG WITH LIBFREETYPE ---

# Only for the burned-in frame numbers on the review proxy, which need the
# drawtext filter, which needs an ffmpeg built with libfreetype. Homebrew's
# bottle is not, and on that machine the app simply leaves the numbers out.
#
# So every option here is optional by definition, and the labels say so. The
# download is listed first on macOS rather than last, because the prebuilt
# binaries already include freetype and rebuilding ffmpeg from source to get a
# frame counter is not a reasonable thing to ask of anyone.
FREETYPE_INSTALL = {
    "Windows": [
        ("Standard Windows builds already include this", None, "https://www.gyan.dev/ffmpeg/builds/"),
    ],
    "Darwin": [
        ("Optional — a prebuilt binary that includes it", None, "https://evermeet.cx/ffmpeg/"),
        (
            "Or build Homebrew's ffmpeg with freetype",
            "brew tap homebrew-ffmpeg/ffmpeg && brew install homebrew-ffmpeg/ffmpeg/ffmpeg --with-freetype",
            None,
        ),
    ],
    "Linux": [
        ("Debian and Ubuntu builds already include this", "sudo apt install ffmpeg", None),
        ("Or a prebuilt binary", None, "https://johnvansickle.com/ffmpeg/"),
    ],
}

FREETYPE_FALLBACK = [
    ("Optional — an ffmpeg built with libfreetype", None, "https://ffmpeg.org/download.html"),
]

# --- PYTHON ---

# The download comes first here, unlike ffmpeg: someone whose Python is too old
# is usually not the person who already has Homebrew set up.
PYTHON_INSTALL = {
    "Windows": [
        ("Download an installer", None, "https://www.python.org/downloads/"),
        ("Or with winget", "winget install Python.Python.3.11", None),
    ],
    "Darwin": [
        ("Download an installer", None, "https://www.python.org/downloads/"),
        ("Or with Homebrew", "brew install python@3.11", None),
    ],
    "Linux": [
        ("Debian and Ubuntu", "sudo apt install python3.11", None),
        ("Or download the source", None, "https://www.python.org/downloads/"),
    ],
}

PYTHON_FALLBACK = [
    ("Download an installer", None, "https://www.python.org/downloads/"),
]
