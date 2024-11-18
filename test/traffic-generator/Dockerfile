FROM python:alpine

COPY ./config.py ./gen.py /
RUN pip install requests

CMD [ "python", "/gen.py" ]