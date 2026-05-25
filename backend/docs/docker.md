# Docker Hub 镜像加速

### 安装Docker

官方安装脚本（国外机器使用）：

```
curl -fsSL https://get.docker.com | sh
```
清华大学源（国内机器使用）
```
bash <(curl -sSL https://gitee.com/wanfeng789/shell/raw/master/install.sh) --mirror Tuna
```

国内安装脚本(支持多种系统)  [(脚本来源)](https://linuxmirrors.cn/other/)

```
bash <(curl -sSL https://gitee.com/wanfeng789/shell/raw/master/docker.sh)
```

<details>
   <summary> 手动离线安装Docker </summary>
  
####  下载 Docker:

[官方文件下载地址——下载后上传到root目录](https://download.docker.com/linux/static/stable/x86_64/)

[国内请点这里清华大学下载地址](https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/static/stable/x86_64/)

```
tar xzvf docker-26.1.3.tgz     # 替换你实际下载的版本号
sudo mv docker/* /usr/local/bin/
```
#### 创建 Docker 服务文件
```
sudo vim /etc/systemd/system/docker.service
```
添加以下内容
```
[Unit]
Description=Docker Application Container Engine
After=network-online.target firewalld.service
Wants=network-online.target

[Service]
Type=notify
ExecStart=/usr/local/bin/dockerd
ExecReload=/bin/kill -s HUP $MAINPID
Restart=always
RestartSec=2
StartLimitBurst=3
StartLimitInterval=60s
LimitNOFILE=infinity
LimitNPROC=infinity
LimitCORE=infinity
Delegate=yes
KillMode=process

[Install]
WantedBy=multi-user.target
```

#### 启动并启用 Docker 服务
```
sudo chmod +x /usr/local/bin/dockerd
sudo systemctl daemon-reload
sudo systemctl start docker
sudo systemctl enable docker
```
#### 查看版本
```
docker -v
```

</details>



<details>
   <summary> 手动离线安装Docker-compose </summary>
  


***国内环境手动安装Docker-compose***

[点这里手动下载文件](https://github.com/docker/compose/releases) 上传到服务器的`/usr/local/bin`目录

地址：https://github.com/docker/compose/releases

无法访问github可以参考这里： https://gitee.com/wanfeng789/github

重命名为docker-compose
```
sudo cp docker-compose-linux-x86_64 /usr/local/bin/docker-compose
```

增加执行权限
```
chmod +x /usr/local/bin/docker-compose
```

验证安装
```
docker-compose --version
```

####  注意：
由于是以二进制文件安装的`docker-compose`，所以运行命令有所变化，运行示例
```
docker-compose up -d
```

区别在于中间的`-`，官方安装脚本是以插件形式安装的`docker-compose`，所以中间不需要`-`




</details>






## 配置加速地址

> Ubuntu 16.04+、Debian 8+、CentOS 7+

创建或修改 `/etc/docker/daemon.json`：

```
sudo mkdir -p /etc/docker
```
```
sudo tee /etc/docker/daemon.json <<EOF
{
    "registry-mirrors": [
        "https://docker.m.ixdev.cn",
        "https://docker.1ms.run"
    ]
}
EOF
```

```
sudo systemctl daemon-reload
```
```
sudo systemctl restart docker
```

#### 提示：如果不方便重启Docker服务，也可以不用设置全局加速地址，拉取镜像时增加加速地址即可，示例：
```
docker pull docker.1panel.live/library/mysql:5.7
```
说明：`library`是一个特殊的命名空间，它代表的是官方镜像。如果是某个用户的镜像就把`library`替换为镜像的用户名。

### Docker Desktop 配置

对于电脑的`Docker Desktop`用户，点击右上角`设置`，找到`Docker Engine`然后修改配置，修改后的示例：
```
{
  "builder": {
    "gc": {
      "defaultKeepStorage": "20GB",
      "enabled": true
    }
  },
  "experimental": false,
  "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.1panel.live"
  ]
}
```
然后点击右下角的`Apply & restart`保存并重启即可。


### 检查加速是否生效

查看docker系统信息 `docker info`，如果从结果中看到了你配置的加速地址，说明配置成功。

```
Registry Mirrors:
 [...]
 https://docker.1panel.live
```

## 使用代理拉取镜像

- 注意：使用了加速源就别使用这个方法了

#### 创建配置文件
```
sudo mkdir -p /etc/systemd/system/docker.service.d
```

```
sudo vim /etc/systemd/system/docker.service.d/http-proxy.conf
```

#### 在文件中添加代理
```
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:1080"
Environment="HTTPS_PROXY=http://127.0.0.1:1080"
Environment="NO_PROXY=localhost,127.0.0.1"
```
#### 重启Docker
```
sudo systemctl daemon-reload
sudo systemctl restart docker
```

#### 查看环境变量
```
sudo systemctl show --property=Environment docker
```

#### 本地流量转发到服务器

使用SSH反向转发把本地的10808端口的流量转发给远程服务器1080端口
```
ssh -R 1080:127.0.0.1:10808 root@服务器地址 -N
```
`-N` 代表仅连接但不打开对话框



---
## 备用方法：打包镜像到本地


1：压缩保存镜像到本地

```
docker save 镜像名 > 镜像名.tar
```

2：手动上传到另一个服务器

3：另一个服务器解压镜像

```
docker load < 镜像名.tar
```
4：查看镜像
```
docker images
```
---

## Docker Hub 镜像测速

拉取镜像时，可使用 `time` 统计所花费的总时间。测速前记得移除本地的镜像。

例如：`time docker pull node:latest`



## 修改客户端并发数加快下载速度

`/etc/docker/daemon.json`

```
{
  "registry-mirrors": [
    "https://docker.m.ixdev.cn",
    "https://docker.1ms.run"
  ],
  "max-concurrent-downloads": 10,
  "max-concurrent-uploads": 10,
  "max-download-attempts": 5,
  "default-ulimits": {
    "nofile": {
      "Hard": 64000,
      "Name": "nofile",
      "Soft": 64000
    }
  }
}
```
```
sudo systemctl daemon-reload
sudo systemctl restart docker
```


## 为Docker启用IPV6

创建或修改`/etc/docker/daemon.json`文件

增加如下配置：
```
{
  "ipv6": true,
  "fixed-cidr-v6": "fd00:1::/64"
}
```
重启：`sudo systemctl restart docker`

## 卸载Docker
```
sudo systemctl stop docker
sudo apt-get purge docker-ce docker-ce-cli containerd.io
sudo rm -rf /etc/docker /var/lib/docker
```
---
## Docker最新稳定加速源列表

> 企业级优质稳定加速源

提供者 | 镜像加速地址 | 说明 | 加速类型
--- | --- | --- | ---
[CNIX](https://m.ixdev.cn/) | `https://docker.m.ixdev.cn` | 无限制&多仓库支持 | Docker Hub
[1panel](https://1panel.cn/docs/user_manual/containers/setting/) | `https://docker.1panel.live` | 无限制 | Docker Hub
[轩辕镜像](https://docker.xuanyuan.me/) | `https://docker.xuanyuan.me` | 无限制 | Docker Hub
[毫秒镜像](https://docker.1ms.run) | `https://docker.1ms.run` | 有黑名单&可选国内cdn | Docker Hub
[DaoCloud](https://github.com/DaoCloud/public-image-mirror) | `https://docker.m.daocloud.io` |白名单和限流 | Docker Hub
[华为云](https://console.huaweicloud.com/swr/#/swr/dashboard) | `https://***.mirror.swr.myhuaweicloud.com` | 需登录分配 | Docker Hub
[腾讯云](https://cloud.tencent.com/document/product/1207/45596) | `https://mirror.ccs.tencentyun.com` | 仅限腾讯云机器 | Docker Hub
[南京大学](https://doc.nju.edu.cn/books/e1654) | `https://ghcr.nju.edu.cn` | ghcr加速 | ghcr
[南京大学](https://doc.nju.edu.cn/books/e1654) | `https://k8s.nju.edu.cn` | k8s加速 | k8s
[CNIX](https://m.ixdev.cn/) | `https://ghcr.m.ixdev.cn` | 无限制&多仓库支持 | ghcr