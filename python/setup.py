from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="agentlens",
    version="0.1.0",
    author="AgentLens Contributors",
    description="Lightweight observability for AI agent pipelines — DevTools for agents",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/speed785/agentlens",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.9",
    install_requires=[],
    extras_require={
        "openai": ["openai>=1.0.0"],
        "anthropic": ["anthropic>=0.20.0"],
        "all": ["openai>=1.0.0", "anthropic>=0.20.0"],
        "dev": [
            "pytest>=7.0",
            "pytest-asyncio>=0.21",
            "black",
            "mypy",
            "ruff",
        ],
    },
    entry_points={
        "console_scripts": [
            "agentlens=agentlens.__main__:main",
        ],
    },
)
