from setuptools import setup, find_packages

setup(
    name="cirvanna",
    version="1.0.0",
    description="Cirvanna Virtual Try-On Core Infrastructure",
    author="Cirvanna Inc.",
    author_email="dev@cirvanna.com",
    packages=find_packages(),
    install_requires=[
        line.strip() for line in open("requirements.txt").readlines()
    ],
    python_requires=">=3.9",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: Other/Proprietary License",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Multimedia :: Graphics :: 3D Modeling",
    ],
    include_package_data=True,
    zip_safe=False,
)
