#! /usr/bin/env python

################################################################################
#
# Please consult the README for information on modifying these scripts and 
# getting configuring LDAP to work with them.
#
################################################################################

import ldap, ldap.sasl, ldif, getpass, sys, os
from subprocess import *
from StringIO import StringIO
from collections import namedtuple

# Configuration
server = "master.sec.com:389"
basedn = "dc=pplive,dc=cn"
maildomain = "pptv.com"

################################################################################
# Changetypes
# For the most part, these map to the same changetypes that you would use in an
# LDIF processed by ldapmodify. 
#
# The exception is Transform, which is unique to these scripts. Since I wanted
# the functions to generate a list of changes to make instead of making the
# changes themselves, modifying values that contain data we want to keep (such
# as gecos) became problematic. Transform allows us to take in the data and
# return the modified version later, once we have a connection to the directory.
#
################################################################################
Add = namedtuple("Add","dn modlist")
Modify = namedtuple("Modify","dn modlist")
Delete = namedtuple("Delete","dn")
RDNMod = namedtuple("RDNMod","dn new flag")
Transform = namedtuple("Transform","dn attr fun")

def getNextId(database="passwd"):
    """Return the next available id for the provided getent(1) database."""
    getent = Popen(["getent", database], stdout=PIPE)
    awk = Popen(["awk", "-F:", "($3>1000) && ($3<10000) && ($3>maxuid) { maxuid=$3; } END { print maxuid+1; }"],stdin=getent.stdout,stdout=PIPE)
    getent.stdout.close()
    highest = awk.communicate()[0]
    return highest.strip()

def getBindDn(user=""):
    """Return a DN for binding as the current logged in user. 
    
    This function assumes that the uid 'user' maps to the DN uid=user,ou=People
    beneath the base DN."""
    username = user or getpass.getuser()
    binddn = "uid=%s,ou=People,%s" % (username,basedn)
    return binddn

def getUsername(dn):
    """Get the uid/cn of the given DN."""
    return dn.split(',')[0].split('=')[1]

def chainUpdate(l, value, position):
    """Update a list and return it."""
    l[position] = value
    return l

def gecosChange(value, position):
    """Return a lambda that can modify a gecos at the spcified position."""
    return lambda gecos : ','.join(chainUpdate(gecos.split(','),value,position))

def useradd(user,uid,groups,shadow_change,gid,name="",home="",shell="/bin/bash",gecos="",passwd='{CRYPT}crivPCxzfxzAA',room='',phone='',other=''):
    uid = str(uid) if uid else getNextId()
    name = user if not name else name
    home = home if home else "/home/%s" % user
    dn = "uid=%s,ou=People,%s" % (user, basedn)
    results = []
    attrs = [ ('uid', [user]),
              ('cn', [name]),
              ('sn', [name]),
              ('objectClass', ['inetOrgPerson', 'posixAccount', 'person', 'shadowAccount','organizationalPerson']),
              ('shadowMax', ['90']),
              ('shadowWarning', ['89']),
              ('loginShell', [shell]),
              ('uidNumber', [uid]),
              ('gidNumber', [gid]),
              ('userPassword',[passwd]),
              ('shadowLastChange',[shadow_change]),
              ('homeDirectory', ["/home/%s" % user]),
              ('mail', ["%s@%s" % (user, maildomain)]),
              ('gecos', [gecos if gecos else "%s,%s,%s,%s" % (name,room,phone,other)]) ]
    results.append(Add(dn,attrs))
    results.extend(usermod(user,groups=groups,append=True))
    return results

def groupadd(group,gid,desc):
    gid = str(gid) if gid else getNextId(database="group")
    dn = "cn=%s,ou=Group,%s" % (group, basedn)
    results = []
    attrs = [ ('objectClass', ['posixGroup']),
              ('cn', group),
              ('gidNumber', gid),
              ('description',desc) ]
    results.append(Add(dn,attrs))
    return results

def groupmems(add="",delete="",group="",list=False,purge=False):
    if not group:
        raise Exception("Expected a group name.")
    elif not (add or delete or list or purge):
        raise Exception("Expected an action.\nPossible actions include:\n\t--add\n\t--delete\n\t--list\n\t--purge")
    dn = "cn=%s,ou=Group,%s" % (group, basedn)
    attrs = []
    if add:
        attrs.append((ldap.MOD_ADD,'memberUid',add))
    if delete:
        attrs.append((ldap.MOD_DELETE,'memberUid',delete))
    if purge: 
        # None indicates that all values for this attribute should be deleted
        attrs.append((ldap.MOD_DELETE,'memberUid',None))
    if list:
        # This will need to fetch and format all of the users in this group.
        raise Exception("groupmems cannot list users yet")
    return [Modify(dn,attrs)]

def groupmod(group,name="",gid=0):
    dn = "cn=%s,ou=Group,%s" % (group, basedn)
    results = []
    attrs = []
    if name:
        results.append(RDNMod(dn, "cn=%s" % name, True))
    if gid:
        attrs.append((ldap.MOD_REPLACE, 'gidNumber', gid))
    results.insert(0, Modify(dn,attrs))
    return results   

def usermod(user,groups=[],append=False,home="",name="",expiredate="",inactive=0,gid=0,login="",lock=False,move_home=False,shell="",uid=0,unlock=False,room='',phone='',other=''):
    dn = "uid=%s,ou=People,%s" % (user, basedn)
    results = []
    attrs = []
    if groups:
        if append:
            for x in groups:
                results.extend(groupmems(add=user,group=x))
        else:
            raise Exception("Removal of users from groups through usermod is not yet supported. Please use groupmems.\nGroups not affected.")
    if home:
        if move_home:
            raise Exception("Currently, usermod does not create a users home directory.")
        else:
            attrs.append((ldap.MOD_REPLACE, 'homeDirectory', home))
            print("Note that without the --move-home option, the users files will all remain in their old home directory.")
    if name:
        attrs.append((ldap.MOD_REPLACE, 'cn', name))
        results.append(Transform(dn,"gecos",gecosChange(name,0)))
    if room:
        attrs.append((ldap.MOD_REPLACE, 'roomNumber', room))
        results.append(Transform(dn,"gecos",gecosChange(room,1)))
    if phone:
        attrs.append((ldap.MOD_REPLACE, 'homePhone', phone))
        results.append(Transform(dn,"gecos",gecosChange(phone,3)))
    if expiredate:
        #attrs.append((ldap.MOD_REPLACE, '?', expiredate))
        raise Exception("usermod currently doesn't update password expiration dates.")
    if inactive:
        attrs.append((ldap.MOD_REPLACE, 'shadowWarning', inactive))
    if gid:
        gid = str(gid)
        attrs.append((ldap.MOD_REPLACE, 'gid', gid))
    if login:
        # This will require changing the actual record, which will require slightly different changes.
        results.append(RDNMod("uid=%s,ou=People,%s" % (user, basedn), "uid=%s" % login, True))
    if lock:
        # This will require some string manipulation of the crypted password. An exclamation point (!) must be added in front of the crypted password.
        attrs.append((ldap.MOD_REPLACE, 'loginShell', "/usr/sbin/nologin"))
        results.append(Transform(dn,"userPassword",lambda pw: pw if pw.startswith("!") else "!" + pw))
    if shell:
        attrs.append((ldap.MOD_REPLACE, 'loginShell', shell))
    if uid:
        uid = str(uid)
        attrs.append((ldap.MOD_REPLACE, 'uid', uid))
    if unlock:
        # This will require some string manipulation of the crypted
        # password. An exclamation point (!) must be remove from the front
        # of the crypted password.
        attrs.append((ldap.MOD_REPLACE, 'loginShell', "/bin/bash"))
        results.append(Transform(dn,"userPassword",lambda pw: pw[1:] if pw.startswith("!") else pw))
    moddeduser = Modify(dn,attrs)
    results.insert(0, moddeduser)
    return results

def handleLDIF(connection, ldif):
    """Handle processing a given LDIF using the provided connection."""
    action = type(ldif)
    try:
        if action == Add:
            connection.add_s(ldif.dn,ldif.modlist)
        elif action == Delete:
            connection.delete_s(ldif.dn,ldif.modlist)
        elif action == Modify:
            connection.modify_s(ldif.dn,ldif.modlist)
        elif action == RDNMod:
            connection.modrdn_s(ldif.dn,ldif.new,ldif.flag)
        elif action == Transform:
            a = connection.search_s(ldif.dn,ldap.SCOPE_SUBTREE, '(objectClass=person)', [ldif.attr])[0][1][ldif.attr]
            modlist = map(lambda y: (ldap.MOD_REPLACE, ldif.attr,ldif.fun(y)),a)
            connection.modify_s(ldif.dn,modlist)
        else:
            raise Exception("Unknown action type.")
    except ldap.TYPE_OR_VALUE_EXISTS:
        print("The value that you are trying to apply to attribute in '%s' is already set and exists." % ldif.dn)
        print(ldif)
    except ldap.ALREADY_EXISTS:
        print("This value already exists in the directory:")
        print(ldif)    
    except ldap.INSUFFICIENT_ACCESS:
        print "You do not have sufficient access to perform:", ldif
    except ldap.NO_SUCH_OBJECT:
        print "No appropriate object was found in the directory. This may be caused by a previous failure to add an object that you are now trying to modify. The associated change is:", ldif

def getConnection(dn, server, passwd="pp12!@", external=False, secure=False):
    # Try to use external SASL authentication if we want it, are root,
    # or no dn was specified with which we should bind.
    #external = not os.getuid() or external or not dn
    connection = ldap.initialize("ldapi:///" if external else "ldap://%s" % server)
    try:
        if secure: connection.start_tls_s()
        if external:
            connection.sasl_interactive_bind_s("",ldap.sasl.external())
        else:
            # If a password hasn't been given, request one.
            passwd = passwd if passwd else getpass.getpass("Password for " + getUsername(dn) + ": ")
            connection.bind_s(dn, passwd, ldap.AUTH_SIMPLE)
    except ldap.SERVER_DOWN:
        print("It would seem that the server is down. Please check your internet connection.")
        if secure: print("You have attempted to connect securely. It may be that the LDAP server does not support secure connections.")
    except ldap.INVALID_CREDENTIALS:
        print("The provided credentials were incorrect. Please try again.")
    except ldap.LDAPError, e:
        print e.message['info']
        if type(e.message) == dict and e.message.has_key('desc'):
            print e.message['desc']
        else:
            print e
    else:
        return connection

def update(actions):
    connection = getConnection('cn=Manager,dc=pplive,dc=cn',server)
    try:
        # Process all of our actions.
        map(lambda action : handleLDIF(connection,action),actions)
    finally:
        connection.unbind()

def get_groups():
    connection = getConnection('cn=Manager,dc=pplive,dc=cn',server)
    try:
        l = []
        groups = connection.search_s('ou=Group,dc=pplive,dc=cn',1)
        for g in groups:
            l.append(g[1]['cn'][0])
        return l
    finally:
        connection.unbind()

def get_group_userlist(g_name):
    connection = getConnection('cn=Manager,dc=pplive,dc=cn',server)
    try:
        groups = connection.search_s('cn=%s,ou=Group,dc=pplive,dc=cn' % g_name,2)
        return groups[0][1]['memberUid']
    finally:
        connection.unbind()    

def get_users():
    connection = getConnection('cn=Manager,dc=pplive,dc=cn',server)
    try:
        l = []
        groups = connection.search_s('ou=People,dc=pplive,dc=cn',1)
        for g in groups:
            l.append(g[1]['cn'][0])
        return l
    finally:
        connection.unbind()
