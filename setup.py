from setuptools import find_packages, setup


setup(
    name="fixsub",
    version="0.1.0",
    description="On-demand Chinese subtitle search, validation, and sync CLI",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "typer>=0.12.0",
        "rich>=13.0.0",
        "httpx>=0.27.0",
        "charset-normalizer>=3.3.0",
    ],
    extras_require={
        "dev": [
            "pytest>=8.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "fixsub=fixsub.cli:app",
        ],
    },
)
