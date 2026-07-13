from create_s3 import create_s3
from create_dynamodb import create_tables
from create_eventbridge import create_eventbridge
from create_iam import create_roles

def main():
    create_roles()
    create_s3()
    create_tables()
    create_eventbridge()

if __name__ == "__main__":
    main()