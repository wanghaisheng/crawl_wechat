import os
import json

search_set = set()
home_path = os.path.join(os.path.expanduser('~'), 'weixin')
if os.path.exists(home_path):
    pass
else:
    os.mkdir(home_path)

account_db = os.path.join(home_path, '.account')
if os.path.exists(account_db):
    with open(account_db, 'r', encoding='utf8') as f:
        for item in json.loads(f.read()):
            search_set.add(tuple(item))

search_set.add(('chengxuyuanxiaohui', '程序员小灰'))
search_set.add(('程序员小灰', '程序员小灰'))
search_set.add(('DevOps技术栈', 'DevOps技术栈'))
search_set.add(('devops8', 'DevOps技术栈'))
search_set.add(('Go 101', 'golang101'))
search_set.add(('Go 101', 'Go 101'))
search_set.add(('golangchina', 'GoCN'))
search_set.add(('GoCN', 'GoCN'))
search_set.add(('gh_c5b565adc4bf', 'Go工程实践'))
search_set.add(('Go工程实践', 'Go工程实践'))
search_set.add(('AsongDream', 'Golang梦工厂'))
search_set.add(('Golang梦工厂', 'Golang梦工厂'))
search_set.add(('cloud_native_yang', '云原生实验室'))
search_set.add(('云原生实验室', '云原生实验室'))
search_set.add(('CloudNativeDomain', '云原生领域'))
search_set.add(('云原生领域', '云原生领域'))
search_set.add(('xuanmairen', '轩脉刃的刀光剑影'))
search_set.add(('轩脉刃的刀光剑影', '轩脉刃的刀光剑影'))
search_set.add(('xiaobaidebug', '小白debug'))
search_set.add(('小白debug', '小白debug'))
search_set.add(('微服务实践', '微服务实践'))
search_set.add(('zeromicro', '微服务实践'))
search_set.add(('kevin_tech', '网管叨bi叨'))
search_set.add(('网管叨bi叨', '网管叨bi叨'))
search_set.add(('iamtonybai', 'TonyBai'))
search_set.add(('TonyBai', 'TonyBai'))
search_set.add(('TechGoPaper', 'TechPaper'))
search_set.add(('TechPaper', 'TechPaper'))
search_set.add(('qiyacloud', '奇伢云存储'))
search_set.add(('奇伢云存储', '奇伢云存储'))
search_set.add(('Python之美', 'Python之美'))
search_set.add(('python_cn', 'Python之美'))
search_set.add(('polarisxu', 'polarisxu'))
search_set.add(('xu_polaris', 'polarisxu'))
search_set.add(('peachesTao', 'peachesTao'))
search_set.add(('gh_1a78ded3e163', 'peachesTao'))
search_set.add(('niuniu_mart', '牛牛码特'))
search_set.add(('牛牛码特', '牛牛码特'))
search_set.add(('脑子进煎鱼了', '脑子进煎鱼了'))
search_set.add(('eddycjy', '脑子进煎鱼了'))
search_set.add(('mohuishou', 'mohuishou'))
search_set.add(('lailinxyz', 'mohuishou'))
search_set.add(('貘艺', '貘艺'))
search_set.add(('TapirGames', '貘艺'))
search_set.add(('码农桃花源', '码农桃花源'))
search_set.add(('CoderPark', '码农桃花源'))
search_set.add(('Kubernetes 生态圈', 'Kubernetes 生态圈'))
search_set.add(('k8sstack', 'Kubernetes 生态圈'))
search_set.add(('K8S中文社区', 'K8S中文社区'))
search_set.add(('k8schina', 'K8S中文社区'))
search_set.add(('架构之美', '架构之美'))
search_set.add(('beautyArch', '架构之美'))
search_set.add(('架构算法', '架构算法'))
search_set.add(('gh_fd99d443991a', '架构算法'))
search_set.add(('架构师之路', '架构师之路'))
search_set.add(('road5858', '架构师之路'))
search_set.add(('HHFCodeRv', 'HHFCodeRv'))
search_set.add(('hhfcodearts', 'HHFCodeRv'))
search_set.add(('光谷码农', '光谷码农'))
search_set.add(('guanggu-coder', '光谷码农'))
search_set.add(('Go招聘', 'Go招聘'))
search_set.add(('golangjob', 'Go招聘'))
search_set.add(('Go语言中文网', 'Go语言中文网'))
search_set.add(('studygolang', 'Go语言中文网'))
search_set.add(('Go语言进阶', 'Go语言进阶'))
search_set.add(('go-kratos', 'Go语言进阶'))
search_set.add(('talkgo_night', 'Go夜读'))
search_set.add(('Go夜读', 'Go夜读'))
search_set.add(('Go生态', 'Go生态'))
search_set.add(('go-ecology', 'Go生态'))

xxx = set()
for item in search_set:
    if item[0] != item[1]:
        pass
    else:
        xxx.add(item[0])

with open(account_db, 'w', encoding='utf8') as f:
    f.write(json.dumps(list(xxx), ensure_ascii=False))
