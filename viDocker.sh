run(){
	echo -n "$*"
	bash -c "$*"
	echo "==> $?"
}

#check priviledge
if [ "$(id -u)" != "0" ];then
	echo "must run as root user, please use sudo"
	exit 1
fi

#install packages
which brctl >/dev/null
if [ $? != 0 ];then
	echo "install packages required now"
	apt-get install bridge-utils
	if [ $? != 0 ];then
		echo "failed to get package"
		exit 1
	fi
fi

IFINDEX=eth0
IMAGE=$1
DOCKER_NAME=$2
#check mandantory parameters
if [ "x$IMAGE" = "x" -o "x$DOCKER_NAME" = "x" ];then
	echo "usage: $0 <docker image> <docker name>"
	exit 1
fi

#check existance of the image
if [ "$(docker images -q $IMAGE)" = "" ];then
	echo "can not find image \"$IMAGE\""
	exit 1
fi

#docker running options
DOCKER_OPTIONS=--privileged=true
USER=vv
PASSWD=vv
UID=1000
GID=1000

#remove jail for dhclient in docker instance
apparmor_status | grep dhclient
if [ $? = 0 ];then
	apparmor_parser -R /etc/apparmor.d/sbin.dhclient 
fi

startContainer(){
	TEMP=$(docker ps -a -f name=$DOCKER_NAME | grep $DOCKER_NAME)
	if [ $? != 0 ];then
		echo $(createContainer $IMAGE)
		return 0
	fi

	TEMP=$(docker ps -f name=$DOCKER_NAME | grep $DOCKER_NAME)
	if [ $? != 0 ];then
		# it is stopped
		CONTAINER=$(docker start $DOCKER_NAME)
		if [ $? != 0 ];then
			echo "start container $DOCKER_NAME failed"
			exit 2
		fi
	fi

	#get container ID from name
	CONTAINER=$(docker inspect --format='{{ .Id }}' $CONTAINER)
	CONTAINER=$(expr substr $CONTAINER 1 12)
	echo $CONTAINER
}

createContainer(){
	IMAGE=$1
	#CONTAINER=$(docker run -u $UID:$GID --group-add=[sudo] --net=none -dt $DOCKER_OPTIONS $IMAGE )
	CONTAINER=$(docker run -u $UID:$GID --net=none --hostname=$DOCKER_NAME --add-host=$DOCKER_NAME:127.0.0.1 --name=$DOCKER_NAME -dt $DOCKER_OPTIONS $IMAGE )
	if [ $? != 0 ];then
		echo "start container image $IMAGE failed"
		exit 1
	fi
	CONTAINER=$(expr substr $CONTAINER 1 12)
	echo $CONTAINER
}


setupNetns(){
	#set symbol link to show up netns
	CONTAINER=$1
	OPCODE=$2
	NAMESPACE=$(docker inspect --format='{{ .State.Pid }}' $CONTAINER)
	if [ "$OPCODE" = "add" ];then
		run mkdir -p /var/run/netns
		run ln -s /proc/$NAMESPACE/ns/net /var/run/netns/$NAMESPACE
	else
		run unlink /var/run/netns/$NAMESPACE
	fi
}

findIntf(){
	ip -o link |cut -d\  -f2|grep $1 > /dev/null
	if [ $? = 0 ];then
		return 1
	fi
	return 0
}

createBridge(){
	findIntf $1
	if [ $? = 1 ];then
		echo "already created bridge $1"
		return 1
	fi

	run brctl addbr $1
	run ifconfig $1 up
	return 1
}

moveHostIntf(){
	IFINDEX=$1
	BRIDGE=bridge-$IFINDEX

	bridge link show|cut -d\  -f 2|grep "^$IFINDEX\$"
	#brctl show $BRIDGE | grep "\<$IFINDEX\>" >/dev/null
	if [ $? = 0 ];then
		echo "host interface $IFINDEX already in bridge $BRIDGE"
		return 1
	fi

	#save route table related to this interface
	myRoute=$(ip route show scope global dev $IFINDEX | while read dst via gw;do if [ "$via" = "via" ]; then echo "route add -net $dst gw $gw";fi;done;)

	#save IP of this interface
	myIp=$(getIpAddr $IFINDEX)
	
	run ip addr flush dev $IFINDEX
	run brctl addif $BRIDGE $IFINDEX

	#restore IP of the old interface to new one
	run ifconfig $BRIDGE $myIp

	#restore route table related to this interface
	for r in "$myRoute";do
		run $r
	done

}

getIpAddr(){
	ip addr show $1|grep -o "inet [^[:space:]]*"|cut -d\  -f2
}
getMacAddr(){
	ip link show $1|grep -o "link/ether [^[:space:]]*"|cut -d\  -f2
}
setMacAddr(){
	run ip link set address $2 dev $1
}

cloneIntfMacAddress(){
	addr=$(getMacAddr $1)
	echo "$1/$2: host side address is $addr"
	setMacAddr $2 $addr
}

attachToBridge(){
	CONTAINER=`expr substr $1 1 6`
	IFINDEX=$2
	BRIDGE=bridge-$IFINDEX
	HOST_IF=h-$IFINDEX-$CONTAINER
	GUEST_IF=g-$IFINDEX-$CONTAINER

	NAMESPACE=$(docker inspect --format='{{ .State.Pid }}' $CONTAINER)
	if [ $? != 0 ];then
		echo "can not find container $CONTAINER"
		return 0
	fi

	findIntf $BRIDGE
	if [ $? = 0 ];then
		echo "bridge $BRIDGE not exist"
		return 0
	fi

	findIntf $HOST_IF
	if [ $? = 1 ];then
		echo "intf $HOST_IF already exist"
		return 1
	fi

	#create veth pair for container
	run ip link add $HOST_IF type veth peer name $GUEST_IF

	#handle $GUEST_IF mac address
	if [ -f "mac-$CONTAINER_ID" ];then
		macAddr=$(cat mac-$CONTAINER_ID)
		echo "using exist mac address $macAddr for $CONTAINER_ID"
		setMacAddr $GUEST_IF $macAddr
	else
		macAddr=$(getMacAddr $GUEST_IF)
		echo "saving mac address $macAddr for $CONTAINER_ID"
		echo "$macAddr" > mac-$CONTAINER_ID
	fi

	run brctl addif $BRIDGE $HOST_IF
	run ifconfig $HOST_IF up

	#move interface into container and setup this interface
	run ip link set $GUEST_IF netns $NAMESPACE name $IFINDEX

	setupNetns $CONTAINER_ID add
	run ip netns exec $NAMESPACE ip link set $IFINDEX up
	#run ip netns exec $NAMESPACE dhclient $IFINDEX 
	setupNetns $CONTAINER_ID remove

	return 1
}

CONTAINER_ID=$(startContainer $IMAGE)
if [ $? != 0 ];then
	exit 1
fi
createBridge bridge-$IFINDEX
moveHostIntf $IFINDEX
attachToBridge $CONTAINER_ID $IFINDEX

#do some setup for this docker instance such as password, sudoer, etc.
docker exec -u root $CONTAINER bash -c "echo '$USER:$PASSWD'|chpasswd"
docker exec -u root $CONTAINER adduser $USER sudo

#instruction to connect to docker instance console
#docker exec -it $CONTAINER bash

#instruction to stop and delete containers
#for i in `docker ps -a|grep "$IMAGE"|cut -d\  -f1|xargs `;do docker stop $i;sudo docker rm $i;done

#docker commit -m "comments" $CONTAINER <repo>:<tag>

