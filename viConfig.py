class viConfig:
    DEF_HOST_USER = 'vv'
    DEF_HOST_PASSWD = 'vv'
    hosts = {
            '192.168.1.118' : 
                {
                    'user' : 'vv',
                    'passwd' : 'vv',
                },
            '192.168.1.119' :
                {},
    }
    
    DEF_GUEST_TYPE = 'viDocker'
    DEF_GUEST_USER = 'guest'
    DEF_GUEST_PASSWD = 'vv'
    DEF_GUEST_PREFIX_LENGTH = '24'
    DEF_GUEST_GATEWAY = '192.168.1.118'
    CREATE_IP='192.168.1.110'
    guests = [
    {'opcode' : 'create', 'ip' : CREATE_IP, 'prefix_length' : '24', 'user' : 'vv', 'passwd' : 'vv', 'host' : '192.168.1.118', 'type' : 'viDocker'},
    {'opcode' : 'join', 'ip' : '192.168.1.111', 'host' : '192.168.1.118'},
    {'opcode' : 'join', 'ip' : '192.168.1.112', 'host' : '192.168.1.118'},
#    {'ip' : '192.168.1.113', 'host' : '192.168.1.119'},
#    {'ip' : '192.168.1.114', 'host' : '192.168.1.119'},
#    {'ip' : '192.168.1.115', 'host' : '192.168.1.119'},
    ]
    
    workDir = 'vivi'
