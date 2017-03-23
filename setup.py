from setuptools import find_packages, setup

setup(
    name='tecken',
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
    packages=find_packages(exclude=['tests', 'tests/*']),
    description='The Mozilla Symbol Server',
    author='Mozilla',
    author_email='peterbe@mozilla.com',
    url='https://github.com/mozilla/tecken',
    license='MPL 2.0',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment :: Mozilla',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Topic :: Internet :: WWW/HTTP',
    ],
    zip_safe=False,
)
