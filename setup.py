#!/usr/bin/env python3
"""
Setup script for Claude Dictate
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

setup(
    name="claude-dictate",
    version="1.0.0",
    author="Claude Dictate Contributors",
    description="Voice-to-Text Tool for Claude Code workflows",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-repo/claude-dictate",
    license="MIT",

    packages=find_packages(),
    package_dir={"": "."},

    python_requires=">=3.9",

    install_requires=[
        "pyaudio>=0.2.13",
        "pynput>=1.7.6",
        "pyperclip>=1.8.2",
        "requests>=2.31.0",
        "customtkinter>=5.2.0",
    ],

    extras_require={
        "whisper": ["openai-whisper>=20231117"],
        "dev": [
            "pytest>=7.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
    },

    entry_points={
        "console_scripts": [
            "claude-dictate=src.main:main",
        ],
    },

    include_package_data=True,
    package_data={
        "": ["templates/*.md"],
    },

    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Desktop Environment",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Multimedia :: Sound/Audio :: Speech",
        "Topic :: Text Processing",
    ],

    keywords="voice-to-text, dictation, whisper, claude, transcription",
)
