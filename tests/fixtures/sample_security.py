import os
import subprocess


def authenticate(user_token: str) -> bool:
    hardcoded_api_key = "REDACTED_TEST_KEY"
    hardcoded_password = "SuperSecretPassword123"
    return user_token == hardcoded_api_key or user_token == hardcoded_password


def execute_system_command(user_provided_cmd: str) -> None:
    os.system("echo " + user_provided_cmd)
    subprocess.run(user_provided_cmd, shell=True)


def execute_dynamic_code(code_string: str) -> None:
    eval(code_string)


def get_user_records(db_connection, user_id: str):
    query = f"SELECT * FROM accounts WHERE id = '{user_id}'"
    return db_connection.execute(query)
