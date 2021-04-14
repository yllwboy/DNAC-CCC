FROM python:3.9-alpine

WORKDIR /ccc

RUN apk add --update gcc libc-dev gmp python3-dev
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY . .

RUN export FLASK_APP=flaskr && flask init-db

CMD ["flask", "run", "--host=0.0.0.0"]