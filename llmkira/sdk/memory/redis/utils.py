# -*- coding: utf-8 -*-
# @Author  : https://github.com/langchain-ai/langchain/blob/master/libs/langchain/langchain/utilities/redis.py
from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
)
from urllib.parse import urlparse

from redis import RedisCluster

if TYPE_CHECKING:
    from redis.client import Redis as RedisType

from loguru import logger


def get_client(redis_url: str, **kwargs: Any) -> RedisType:
    """Get a redis client from the connection url given. This helper accepts
    urls for Redis server (TCP with/without TLS or UnixSocket) as well as
    Redis Sentinel connections.

    Redis Cluster is not supported.

    Before creating a connection the existence of the database driver is checked
    an and ValueError raised otherwise

    To use, you should have the ``redis`` python package installed.

    Example:
        .. code-block:: python

            from langchain.utilities.redis import get_client
            redis_client = get_client(
                redis_url="redis://username:password@localhost:6379"
                index_name="my-index",
                embedding_function=embeddings.embed_query,
            )

    To use a redis replication setup with multiple redis server and redis sentinels
    set "redis_url" to "redis+sentinel://" scheme. With this url format a path is
    needed holding the name of the redis service within the sentinels to get the
    correct redis server connection. The default service name is "mymaster". The
    optional second part of the path is the redis db number to connect to.

    An optional username or password is used for booth connections to the rediserver
    and the sentinel, different passwords for server and sentinel are not supported.
    And as another constraint only one sentinel instance can be given:

    Example:
        .. code-block:: python

            from langchain.utilities.redis import get_client
            redis_client = get_client(
                redis_url="redis+sentinel://username:password@sentinelhost:26379/mymaster/0"
                index_name="my-index",
                embedding_function=embeddings.embed_query,
            )
    """

    # Initialize with necessary components.
    try:
        import redis
    except ImportError:
        raise ValueError(
            "Could not import redis python package. "
            "Please install it with `pip install redis>=4.1.0`."
        )

    # check if normal redis:// or redis+sentinel:// url
    if redis_url.startswith("redis+sentinel"):
        redis_client = _redis_sentinel_client(redis_url, **kwargs)
    elif redis_url.startswith("rediss+sentinel"):  # sentinel with TLS support enables
        kwargs["ssl"] = True
        if "ssl_cert_reqs" not in kwargs:
            kwargs["ssl_cert_reqs"] = "none"
        redis_client = _redis_sentinel_client(redis_url, **kwargs)
    else:
        # connect to redis server from url, reconnect with cluster client if needed
        redis_client = redis.from_url(redis_url, **kwargs)
        if _check_for_cluster(redis_client):
            redis_client
            redis_client.close()
            redis_client = _redis_cluster_client(redis_url, **kwargs)
    return redis_client


def _redis_sentinel_client(redis_url: str, **kwargs: Any) -> RedisType:
    """helper method to parse an (un-official) redis+sentinel url
    and create a Sentinel connection to fetch the final redis client
    connection to a replica-master for read-write operations.

    If username and/or password for authentication is given the
    same credentials are used for the Redis Sentinel as well as Redis Server.
    With this implementation using a redis url only it is not possible
    to use different data for authentication on booth systems.
    """
    import redis

    parsed_url = urlparse(redis_url)
    # sentinel needs list with (host, port) tuple, use default port if none available
    sentinel_list = [(parsed_url.hostname or "localhost", parsed_url.port or 26379)]
    if parsed_url.path:
        # "/mymaster/0" first part is service name, optional second part is db number
        path_parts = parsed_url.path.split("/")
        service_name = path_parts[1] or "mymaster"
        if len(path_parts) > 2:
            kwargs["db"] = path_parts[2]
    else:
        service_name = "mymaster"

    sentinel_args = {}
    if parsed_url.password:
        sentinel_args["password"] = parsed_url.password
        kwargs["password"] = parsed_url.password
    if parsed_url.username:
        sentinel_args["username"] = parsed_url.username
        kwargs["username"] = parsed_url.username

    # check for all SSL related properties and copy them into sentinel_kwargs too,
    # add client_name also
    for arg in kwargs:
        if arg.startswith("ssl") or arg == "client_name":
            sentinel_args[arg] = kwargs[arg]

    # sentinel user/pass is part of sentinel_kwargs, user/pass for redis server
    # connection as direct parameter in kwargs
    sentinel_client = redis.sentinel.Sentinel(
        sentinel_list, sentinel_kwargs=sentinel_args, **kwargs
    )

    # redis server might have password but not sentinel - fetch this error and try
    # again without pass, everything else cannot be handled here -> user needed
    try:
        sentinel_client.execute_command("ping")
    except redis.exceptions.AuthenticationError as ae:
        if "no password is set" in ae.args[0]:
            logger.warning(
                "Redis sentinel connection configured with password but Sentinel \
answered NO PASSWORD NEEDED - Please check Sentinel configuration"
            )
            sentinel_client = redis.sentinel.Sentinel(sentinel_list, **kwargs)
        else:
            raise ae

    return sentinel_client.master_for(service_name)


def _check_for_cluster(redis_client: RedisType) -> bool:
    import redis

    try:
        cluster_info = redis_client.info("cluster")
        return cluster_info["cluster_enabled"] == 1
    except redis.exceptions.RedisError:
        return False


def _redis_cluster_client(redis_url: str, **kwargs: Any) -> RedisCluster:
    from redis.cluster import RedisCluster

    return RedisCluster.from_url(redis_url, **kwargs)
