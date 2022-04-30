import sys, requests, configparser

def get_refresh_token(cp):
    refresh_token = cp.get('DEFAULT', 'refresh_token')

    if not refresh_token:
        sys.exit('Refresh token is not provided in the config file')

    return refresh_token

def request_api_key(cp):
    refresh_token = get_refresh_token(cp)

    endpoint = 'https://login.questrade.com/oauth2/token?grant_type=refresh_token&refresh_token='
    response = requests.get(endpoint + refresh_token)

    if response.status_code != 200:
        msg = f'Error code: {response.status_code}, Error message: {response.content}.'
        sys.exit(msg)

    data = response.json()

    for key, value in data.items():
        cp.set('DEFAULT', str(key), str(value))

    with open('config.txt', 'w') as cpfile:
        cp.write(cpfile)
    
    print('Access requested, check config.txt')

def main():
    cp = configparser.ConfigParser()

    args = sys.argv
    if (len(args) == 1):
        cp.read('config.txt')

    elif (len(args) == 2):
        refresh_token = args[1]
        cp.set('DEFAULT', 'refresh_token', refresh_token)

    request_api_key(cp)

if __name__ == '__main__':
    main()