# awsdjangotest
simple testing repository that is dockerised to be used in an EC2 instance using amazon linux distro

## 1. Install docker and git

sudo yum install -y docker git

sudo systemctl start docker # starts docker deamon and makes docker available to use now

sudo systemctl enable docker # configures docker to start automatically when the system boots up

sudo usermod -aG docker ec2-user # By default, only root can run Docker commands. This gives your regular user (ec2-user) permission to use Docker without sudo every time.

newgrp docker # applys current changes to our session if you run the commands above

Create a new key so that you can push and pull to git, ensure to add it to git
ssh-keygen -t ed25519 -C "Romxsalarda45@gmail.com"

## 2. Install docker compose

sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

docker-compose --version

git clone "my repo"

## 3. run compose

### ENSURE YOU CHECK AND UPDATE CONFIG WHERE NEEDED!

sudo vim .env
sudo vim docker-compose.yaml

1. update .env file, update with credentials,

ALLOWED_HOSTS = <your_ip>

DEBUG = FALSE # for EC2

DB_HOST to "db" instead of "localhost"

Update AWS credentials - create a new AWS secret in the dashboard if you don't have one.

2. update docker-compose.yaml with updates to health check

for database test

test: ["CMD-SHELL", "pg_isready -U <my_postgres_user> -d <my_database_name>"] 

for web - endpoint to test

test: ["CMD", "curl", "http://web:8000"]

3. settings.py changes

if needed, update default security key, but .env should defined one anyway

4. update nginx.conf with s3 bucket

return 301 https://<your_s3_bucket>/static/;

## 4. run to build 

docker-compose up -d --build

docker-compose down 

## 5. After all systems are healthy and running

docker exec django_app python manage.py collectstatic --noinput

docker exec django_app python manage.py makemigrations

docker exec django_app python manage.py migrate

docker exec -it django_app bash 

python manage.py createsuperuser

### 6. to run commands within docker

docker exec -to "container name" "cmd to execute"

to enter django shell (used for py manage.py)
ctrl-d to exit the bash shell once created

docker exec -it django_app bash 

docker logs "app name"
I.e. docker logs django_app

### 7. For setting up TLS/SSL (CLOUDFLARE FULL SSL) - LESS RECOMMENDED

refer to nginx, ensure SSL certificates are ready

mkdir -p ./nginx  # Ensure directory exists
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout ./nginx/cloudflare.key \
    -out ./nginx/cloudflare.crt \
    -subj "/CN=yourdomain.com"

chmod 644 ./nginx/cloudflare.crt
chmod 600 ./nginx/cloudflare.key

## 8. IMPORTANT: For setting up TLS/SSL (CLOUDFLARE FULL STRICT SSL) - RECOMMENDED

sudo pip3 install certbot certbot-nginx
sudo certbot certonly --standalone -d yourdomain.com -d www.yourdomain.com

It will ask a few questions and then populate /etc/letsencrypt/live/... with our certificates
ensure all resources point to there and that docker compose sees the mounted volume - what is a volume?

nginx config
ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

Docker-compose config under nginx
volumes:
    - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf
    - /etc/letsencrypt/live/rsalardadevelop.co.uk/fullchain.pem:/etc/letsencrypt/live/rsalardadevelop.co.uk/fullchain.pem:ro
    - /etc/letsencrypt/live/rsalardadevelop.co.uk/privkey.pem:/etc/letsencrypt/live/rsalardadevelop.co.uk/privkey.pem:ro

Add a cron job for auto renewal
echo "0 0 * * * /usr/local/bin/certbot renew --quiet --post-hook 'systemctl reload nginx'" | sudo tee -a /etc/crontab

## 9. CSRF

In manage.py add this

CSRF_TRUSTED_ORIGINS = [
    'https://yourdomain.com',
    'https://www.yourdomain.com',
]

if not debug:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')  # For Cloudflare/Proxy
    SECURE_SSL_REDIRECT = True  # Force HTTPS
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

## 10. IAM roles for S3 verification

Simply type in IAM in the AWS console, add a new role, select the preset about EC2. 
Then name it whataver, under top right of console -> actions -> security -> modify IAM role and select the one we just made
Done

## 11. Using SSM for paramater store

Ensure in docker-compose.yaml file the database says ${POSTGRES_PASSWORD}

### For manual injection via command line
export POSTGRES_PASSWORD=$(aws ssm get-parameter --name "/prod/db/password" --with-decryption --query "Parameter.Value" --output text)

### For django, use boto3

import boto3

def get_secret(name):
    client = boto3.client('ssm', region_name='your-region')
    return client.get_parameter(Name=name, WithDecryption=True)['Parameter']['Value']

SECRET_KEY = get_secret('/prod/django/secret_key')

## CI/CD

Look at .github/workflows/deploy.yml for the full details of the file. In essence, when a change is made locally, and it's pushed,
the actions file will run, first to build and test, and then deploy to the actual EC2 instance
NOTE: Ensure that the EC2 ID instance paramater in the github secret matches the EC2 instance ID

On the AWS dashboard side, ensure that all the SSM paramaters are setup properly. Ensure the policies attached are correct too.

```
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ssm:SendCommand",
                "ssm:ListCommands",
                "ssm:ListCommandInvocations",
                "ssm:GetCommandInvocation"
            ],
            "Resource": [
                "arn:aws:ec2:eu-west-2:#INSTANCEID#:instance/#EC2-INSTANCE-ID#",
                "arn:aws:ssm:eu-west-2:#INSTANCEID#:document/AWS-RunShellScript"
            ]
        },
        {
            "Effect": "Allow",
            "Action": [
                "ssm:DescribeInstanceInformation",
                "ec2:DescribeInstances"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": [
                "ssm:GetParameter",
                "ssm:GetParameters",
                "ssm:GetParametersByPath"
            ],
            "Resource": "arn:aws:ssm:eu-west-2:#ACCOUNT-ID-OMMITED#:parameter/prod/django/*" # This param changes depending on the SSM configuration set
        }
    ]
}
```

ASWELL AS: AmazonSSMManagedInstanceCore

## FAST START UP
Reminders to do when starting up this EC2 instance
1. Ensure cloudflare has the updated IP
2. Ensure Github Actions has the updated Instance ID and host
3. In settings.py ensure that USING_ENV_FILE is False

then run...
docker-compose up -d 

## Reminders for myself

REMEMBER IMPORTANT:
Create a new Elastic IP, otherwise you have to go onto cloudflare, and change the content IP to the new public IP that
EC2 creates if you dont have an elastic IP.

ENSURE THAT IF NO CERTIFICATE IS IN USE, USE HTTP in the URL. 

CORS is NOT setup yet. 

docker-compose run --rm web python manage.py makemigrations --noinput
docker-compose run --rm web python manage.py migrate --noinput

## TODO:

### Higher Priority
1. Implement monitoring using sentry for Django (done), cloudwatch for EC2 (not yet) 
2. Implementing JWT access token and securing endpoints
3. Finishing of YFC Database API endpoints (in-progress)
4. Test endpoints (in-progress)

### Low priority
1. Implement simple tests in Django
2. Add staging environment - I.e. configure deploy.yml to create a staging environment?
3. add a elastic IP so I dont have to keep changing cloudflare DNS pointer to public IPV4 everytime (costs money though)
4. Switching to RDS instead of local postgres?? (deferred)


Other projects -> To help with SEO, to either learn SSR? or learn how to improve SEO in SPA (single page applications)
