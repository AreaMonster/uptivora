# Firewall rules

## Inbound

| Port | Purpose |
| --- | --- |
| 22/tcp | SSH — restrict to admin addresses where possible |
| 80/tcp | ACME HTTP challenge and redirect to HTTPS |
| 443/tcp, 443/udp | HTTPS (HTTP/3 on UDP) |

Nothing else. PostgreSQL and the application containers are not published.

**Docker bypasses ufw.** Ports published by Docker are opened in iptables ahead of ufw's
rules. The compose files publish only 80/443; do not add `ports:` to other services. Use the
cloud provider's firewall as the outer layer, or rules in the `DOCKER-USER` chain.

## Outbound

The application deliberately needs outbound access, because monitoring means connecting to
arbitrary customer websites. Abuse of that capability (scanning internal networks, cloud
metadata) is prevented in the application: every URL and every redirect target is resolved
and checked against private, loopback, link-local, multicast and reserved ranges, and the
connection is made to the validated address only (DNS-rebinding safe).

The host firewall adds a second layer:

| Destination | Ports | Who |
| --- | --- | --- |
| any public address | 80, 443 (plus whatever ports customers monitor, e.g. 8080, 8443) | worker |
| SMTP server | 587 or 465 | worker |
| DNS resolvers | 53/udp+tcp | all |
| ACME CA (Let's Encrypt, ZeroSSL) | 443 | caddy |
| apt / Docker registries | 443 | host, during updates |

Recommended `DOCKER-USER` rules that block container traffic to private networks — defence in
depth for the SSRF guard (adapt the Docker subnets to `UPTIVORA_SUBNET` and the internal
`data` network):

```bash
# allow established traffic and container-to-container traffic on the Uptivora networks
iptables -I DOCKER-USER 1 -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN
iptables -I DOCKER-USER 2 -s 10.250.48.0/24 -d 10.250.48.0/24 -j RETURN
# block private, link-local (cloud metadata 169.254.169.254) and CGNAT ranges.
# Inserted (-I), not appended: Docker may end the chain with a RETURN rule.
for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 169.254.0.0/16 100.64.0.0/10; do
  iptables -I DOCKER-USER 3 -s 10.250.48.0/24 -d "$net" -j DROP
done
```

If your SMTP relay has a private address, insert a `RETURN` rule for it at position 3 after
running the loop. Traffic between the containers and PostgreSQL uses the separate internal
`data` network and is not affected.

Persist them with `iptables-persistent` (or the nftables equivalent) and test that checks of
public websites still work afterwards. Do the same for IPv6 (`ip6tables`, block `fc00::/7`
and `fe80::/10`) if Docker IPv6 is enabled.

Uptivora itself sends nothing to Uptivora or any analytics service: the only outbound
traffic is in the table above.
