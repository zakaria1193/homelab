# Ansible playbook for my Home Media Server

This is an [Ansible](https://www.ansible.com) playbook to install and configure some apps on my Synology NAS with [Docker](https://www.docker.com).

## Requirements

+ Ansible >= 2.4.0.

## Applications

This playbook is designed to install a bunch of useful apps :

+ [Radarr](https://github.com/Radarr/Radarr)
+ [Sonarr](https://github.com/Sonarr/Sonarr)
+ [Tautulli](https://github.com/Tautulli/Tautulli)
+ [Watchtower](https://github.com/v2tec/watchtower)
+ [Wekan](https://github.com/wekan/wekan)

## Installing on production

Copy the hosts example file and change the values to your needs :

```bash
$ cp hosts.example hosts
```

Then run the playbook :

```bash
$ ansible-playbook -i hosts playbook.yml
```

## Contributing

Do not hesitate to contribute to the project by adapting or adding features ! Bug reports or pull requests are welcome.

## License

This project is released under the [MIT](http://opensource.org/licenses/MIT) license.