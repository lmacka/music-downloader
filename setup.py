from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = []
    for line in fh:
        line = line.strip()
        if line and not line.startswith("#"):
            if "sys_platform == 'win32'" in line:
                # Add Windows-specific dependencies with environment marker
                pkg = line.split(";")[0].strip()
                requirements.append(f"{pkg}; sys_platform == 'win32'")
            else:
                requirements.append(line)

setup(
    name="music-downloader",
    version="2.0.0",
    author="Your Name",
    author_email="your.email@example.com",
    description="A cross-platform music download and organization tool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/music-downloader",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: X11 Applications :: Qt",
        "Environment :: Win32 (MS Windows)",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Topic :: Multimedia :: Sound/Audio",
    ],
    python_requires=">=3.11",
    install_requires=requirements,
    extras_require={
        "dev": [
            "black>=23.12.1",
            "pylint>=3.0.3",
            "pytest>=7.4.4",
            "pytest-asyncio>=0.23.3",
            "pytest-qt>=4.2.0",
            "isort>=5.13.2",
        ]
    },
    entry_points={
        "console_scripts": [
            "music-downloader=music_downloader.__main__:main",
        ],
    },
) 