import tankapiclient
import phout_aggregator
import time
import logging
logging.basicConfig(level=logging.DEBUG)

api_server_1 = 'tank01.haze.yandex.net'
api_server_2 = 'tank02.haze.yandex.net'
api_port = 8888
phout = ''

client1 = tankapiclient.TankapiClient(api_server_1, api_port)
client2 = tankapiclient.TankapiClient(api_server_2, api_port)

logging.info('Preparing 1st')
shoot1 = client1.run_new(
    config_contents=client1.slurp('first.ini'), stage='start')

logging.info(shoot1)

logging.info('Preparing 2nd')
shoot2 = client2.run_new(
    config_contents=client2.slurp('second.ini'), stage='start')

while not client1.destination_reached(shoot1['session'], 'prepare'):
    logging.info('1st not prepared yet')
    time.sleep(5)
logging.info('1st prepared OK')

while not client2.destination_reached(shoot2['session'], 'prepare'):
    logging.info('2nd not prepared yet')
    time.sleep(5)
logging.info('2nd prepared OK')

logging.info('Shooting 1st')
client1.run_given(shoot1['session'])

logging.info('Shooting 2nd')
client2.run_given(shoot2['session'])

while not client1.destination_reached(shoot1['session'], 'finished'):
    logging.info('1st not finished yet')
    time.sleep(30)
logging.info('1st finished OK')

while not client2.destination_reached(shoot2['session'], 'finished'):
    logging.info('2nd not finished yet')
    time.sleep(30)
logging.info('2nd finished OK')

logging.info('Getting 1st artifact_list')
files = client1.artifact_list(shoot1['test'])
for f in files:
    if f.startswith('phout_') and f.endswith('.log'):
        phout = f
        logging.info('1st phout named %s', f)
        break
logging.info('Downloading 1st phout')
client1.artifact_store(shoot1['test'], phout, 'phout1.txt')

logging.info('Getting 2nd artifact_list')
files = client2.artifact_list(shoot2['test'])
for f in files:
    if f.startswith('phout_') and f.endswith('.log'):
        phout = f
        logging.info('2nd phout named %s', f)
        break
logging.info('Downloading 2nd phout')
client2.artifact_store(shoot2['test'], phout, 'phout2.txt')

logging.info('Merging phouts')
phout_aggregator.merge_phouts(['phout1.txt', 'phout2.txt'], 'result_phout.txt')
