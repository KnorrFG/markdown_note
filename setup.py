from distutils.core import setup

packages = ['markdown_note', 'markdown_note.resources']
install_requires = ["markdown", "pyyaml", "toolz", "yattag", "click", "attrdict",
                    "tqdm", 'tabulate']

setup(name='Markdown Note',
      version='0.3',
      author='Felix G. Knorr',
      author_email='knorr.felix@gmx.de',
      packages=packages,
      install_requires=install_requires,
      entry_points = {
        'console_scripts': ['mdn=markdown_note.markdown_note:cli']
      },
      include_package_data=True,
      python_requires='>=3.7')

# Changelog sinc last commit 
#   remove fuzzy matcher which just behaved badly
#   remove ns from timestamps
#   there is probably some documentation missing
#   Increased version to 0.3, i guess i could be more consequent
#   cat supports ls args now
