from setuptools import setup, find_packages

setup(
    name="director",
    version="0.1.0",
    packages=find_packages(include=['director*', 'config*', 'analysis*']),
    install_requires=[
        # Web Framework
        'flask==3.0.3',
        'flask-cors==4.0.1',
        'flask-socketio==5.3.6',
        'openai==1.55.3',
        'openai_function_calling>=0.1.0',
        'anthropic>=0.3.0',
        'tenacity>=8.0.0',
        'replicate>=0.8.0',
        'elevenlabs>=0.2.0',
        'Pillow>=10.0.0',
        'aiohttp>=3.9.0',
        'slack_sdk>=3.27.0',
        'PyJWT>=2.8.0',
        'SQLAlchemy>=2.0.0',
        'PyYAML>=6.0.0',
        'pydantic==2.8.2',
        'pydantic-settings==2.4.0',
        'python-dotenv==1.0.1',
        'videodb',
        'yt-dlp==2024.10.7'
    ],
    python_requires='>=3.8',
) 