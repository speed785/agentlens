from pathlib import Path

from setuptools import setup, find_packages  # pyright: ignore[reportMissingModuleSource]

root_readme = Path(__file__).resolve().parent.parent / "README.md"
long_description = root_readme.read_text(encoding="utf-8") if root_readme.exists() else ""

_ = setup(
    name="agentlens",
    version="0.1.0",
    author="AgentLens Contributors",
    description="Lightweight observability for AI agent pipelines — DevTools for agents",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/speed785/agentlens",
    project_urls={
        "Documentation": "https://github.com/speed785/agentlens#readme",
        "Issues": "https://github.com/speed785/agentlens/issues",
        "Changelog": "https://github.com/speed785/agentlens/blob/main/CHANGELOG.md",
    },
    packages=find_packages(),
    keywords=[
        "ai",
        "agent",
        "llm",
        "profiler",
        "observability",
        "openai",
        "anthropic",
        "monitoring",
        "tracing",
        "opentelemetry",
        "devtools",
        "debugging",
        "performance",
    ],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Software Development :: Libraries",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Software Development :: Debuggers",
        "Topic :: Software Development :: Quality Assurance",
        "Topic :: System :: Monitoring",
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
            "pytest-cov>=4.0",
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
