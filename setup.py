from setuptools import setup

from yandex_tank_api import __version__ as version

with open('requirements.txt') as f:
    requirements = f.readlines()

with open('README.md') as f:
    readme = f.read()


def requireModules(moduleNames=None):
    import re
    if moduleNames is None:
        moduleNames = []
    else:
        moduleNames = moduleNames

    commentPattern = re.compile(r'^\w*?#')
    moduleNames.extend(
        filter(
            lambda line: not commentPattern.match(line),
            requirements))

    return moduleNames


setup(
    name='yandex-tank-api',
    version=version,
    author='Alexey Lavrenuke',
    author_email='direvius@gmail.com',
    description='Yandex.Tank HTTP API',
    long_description=readme,
    classifiers=[
        'Development Status :: 2 - Pre-Alpha', 'Intended Audience :: Developers'
    ],
    setup_requires=[
        'pytest-runner',
        'flake8',
    ],
    install_requires=requirements,
    tests_require=['pytest', ],
    packages=['yandex_tank_api'],
    package_dir={'yandex_tank_api': 'yandex_tank_api'},
    package_data={
        'yandex_tank_api': [
            'templates/*.jade', 'static/css/*.css', 'static/favicon.ico',
            'static/fonts/*', 'static/js/*.js', 'static/js/vendor/ace/*.js',
            'static/js/vendor/*.js', 'config/*'
        ],
    },
    scripts=['scripts/yandex-tank-api-server'],
    test_suite='yandex-tank-api', )
