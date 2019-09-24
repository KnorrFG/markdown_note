from distutils.core import setup
import sys

packages = ['markdown_note', 'markdown_note.resources']
install_requires = ["markdown", "pyyaml", "toolz", "yattag", "click", "attrdict",
                    "fuzzywuzzy[speedup]", "tqdm", 'tabulate']

setup(name='Markdown Note',
      version='0.1',
      author='Felix G. Knorr',
      author_email='knorr.felix@gmx.de',
      packages=packages,
      install_requires=install_requires,
      entry_points = {
        'console_scripts': ['mdn=markdown_note.markdown_note:cli']
      },
      python_requires='>=3.7')
