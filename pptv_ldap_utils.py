import httplib
import simplejson,os
from manageldap import groupadd,update,get_groups,get_users,useradd,get_group_userlist,groupmems

def get_groupinfo_from_cmdb():
    try:
        odb_url = "http://10.203.169.169/odb/ldap_info/"
        conn=httplib.HTTPConnection("10.203.169.169")
        conn.request('GET',odb_url)
        result=conn.getresponse()
        content = result.read()
        conn.close()
        return simplejson.loads(content)
    except:
        return {}

if __name__ == "__main__":
    #
    # Global varaibles
    #
    SHADOW_LAST_CHANGE = os.popen("getent shadow|sort -t: -k3 -nr |head -1").readlines()[0].split(':')[2]
    TEMP_GROUP = 'pptv_temp'
    TEMP_GROUPID = '5001'
    ADMIN_GROUP = 'pptv_admin'

    g_dict = get_groupinfo_from_cmdb()
    cmdb_groups = []
    cmdb_users = {}
    for g in g_dict.keys():
        if g not in cmdb_groups:
            cmdb_groups.append(g)
        for u in g_dict[g]['member']:
            if u[0] not in cmdb_users.keys():
                cmdb_users[u[0]] = u[1]
    '''
        add cmdb group to ldap, if not in yet
    '''
    ldap_groups = get_groups()
    for g in cmdb_groups:
        if g not in ldap_groups:
            print 'creating group in PPTV LDAP',g
            new_g = groupadd(g,g_dict[g]['gid'],g_dict[g]['name'])
            update(new_g)
    '''
        add cmdb user to ldap ,if not in yet
    '''
    ldap_users = get_users()
    for u in cmdb_users.keys():
        if u not in ldap_users:
            print "creating user in PPTV LDAP",u
            new_u = useradd(u,cmdb_users[u],[TEMP_GROUP],SHADOW_LAST_CHANGE,TEMP_GROUPID)
            update(new_u)
    '''
        group memebers cleanup and add new memebers
    '''
    #print get_group_userlist('pptv_temp')
    
    
    