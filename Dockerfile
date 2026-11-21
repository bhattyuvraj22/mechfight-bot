FROM python:3.13.2-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /bot
COPY bot.py combat.py geometry.py navigation.py mechfight.py tactics.py ./
USER 65534:65534
ENTRYPOINT ["python3", "-u", "/bot/bot.py"]
