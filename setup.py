from setuptools import setup

from yandex_tank_api import __version__ as version


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
            open('requirements.txt').readlines()))

    return moduleNames


setup(
    name='yandex-tank-api',
    version=version,
    author='Alexey Lavrenuke',
    author_email='direvius@gmail.com',
    description='Yandex.Tank HTTP API',
    long_description=open('README.txt').read(),
    classifiers=[
        'Development Status :: 2 - Pre-Alpha', 'Intended Audience :: Developers'
    ],
    setup_requires=[
        'pytest-runner',
        'flake8',
    ],
    tests_require=['pytest', ],
    install_requires=[
        "tornado>=2.1",
        "python-daemon>=1.5.5",
        "pyyaml",
        "pyjade",
        "yandextank>=1.8.35",
    ],
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
