import httplib
import simplejson
from manageldap import groupadd,update

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
    #print get_groupinfo_from_cmdb()
    #print '===='
    #newgroup = groupadd('osm-zab')
    #update(newgroup)
    g_dict = get_groupinfo_from_cmdb()
    for g in g_dict.keys():
        print g,g_dict[g]

    