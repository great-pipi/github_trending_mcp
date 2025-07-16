import datetime
import json
import re
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from requests.exceptions import RequestException
from tqdm import tqdm
import base64
import os

import sys

llm = xxxx


from mcp.server.fastmcp import FastMCP
mcp = FastMCP("github-trending")

def remove_unnecessary_content(text: str) -> str:
    """
    移除一些无用的HTML标签、文献参考等
    """
    ref_pattern = re.compile(r'.*?', re.DOTALL)  # 移除参考文献、代码、配置等信息    
    # 简单的HTML标签移除
    removed_content = re.sub(r'<[^>]+>', '', text)
    removed_content = ref_pattern.sub('', removed_content)
    return removed_content

# 更新后的提示词，增加了约束输出格式
FILTER_PROMPT = """
###要求###
请根据下面的Github README信息，精简为仓库描述（即这个仓库是用来做什么的，能达成什么效果，特点是什么），在100-150字之间。
请严格按照以下格式返回：
```json
{{
    "description": "针对这个Github仓库的描述，需要包括这个仓库是用来做什么的，能达成什么效果，特点是什么",
    "is_ai": "True"
}}
```

你不需要在仓库描述中包含以下内容：
- 仓库使用协议
- 仓库引用文献
- 如何配置项目环境、使用仓库的具体代码

###需要处理的仓库 README 内容###
{README_CONTENT}
"""

def clean_json_response(response: str) -> str:
    """清理LLM返回的JSON响应，移除Markdown标记和多余字符"""
    if not response:
        return ""
        
    # 移除```json和```标记
    response = re.sub(r'```json\n', '', response)
    response = re.sub(r'\n```', '', response)
    
    # 移除开头和结尾的引号（如果有）
    response = response.strip()
    if response.startswith('"') and response.endswith('"'):
        response = response[1:-1]
        # 处理转义的引号
        response = response.replace('\\"', '"')
    
    # 处理多余的转义字符
    response = response.replace('\\\\', '\\')
    
    return response

def parse_llm_json_response(response_text: str, llm=llm):
    """解析LLM返回的JSON响应，包含多重错误处理和LLM格式转换兜底"""
    response_text = clean_json_response(response_text)
    
    # 尝试直接解析JSON
    try:
        parsed_json = json.loads(response_text)
        return parsed_json
    except json.JSONDecodeError:
        print(f"直接JSON解析失败: {response_text[:100]}...")
        
        # 尝试从文本中提取JSON块
        json_match = re.search(r'(\{.*\})', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
            try:
                parsed_json = json.loads(json_str)
                return parsed_json
            except json.JSONDecodeError:
                print(f"提取JSON块解析失败: {json_str[:100]}...")
                
                # 使用LLM进行格式转换
                retry_prompt = f"""
                你之前返回的内容:
                {response_text}...
                
                无法被解析为有效的JSON格式。请只返回严格符合JSON格式的数据，不要包含任何其他解释或文本。
                请确保:
                1. 所有字符串使用双引号
                2. 对象键使用双引号
                3. 没有额外的前导或尾随文本
                4. 特殊字符正确转义
                
                例如：
                {{"key": "value", "key": "value"}}
                """
                
                try:
                    # 修改为正确的调用方式
                    retry_response = llm.invoke([{"role": "user", "content": retry_prompt}])
                    retry_cleaned = retry_response.content.strip()  # 获取内容并清理
                    return json.loads(retry_cleaned)
                except Exception as e:
                    print(f"LLM格式转换失败: {str(e)}")
                    return {"error": "LLM格式转换失败", "details": str(e)}
        else:
            return {"error": "未在LLM返回中找到JSON"}


def get_github_trending() -> dict[str, dict]:
    """获取Github Trending上的仓库信息
    - name: 仓库名称
    - url: 仓库地址
    - stars: 仓库的star数量
    - today_stars: 仓库star增长数量
    """
    url = "https://github.com/trending?since=weekly"
    # 设置重试策略
    retry_strategy = Retry(
        total=3,
        status_forcelist=[500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    http = requests.Session()
    http.mount("https://", adapter)
    try:
        response = http.get(url)
        response.raise_for_status()
    except RequestException as e:
        raise RuntimeError(f"Error fetching GitHub trending repositories: {e}")
    
    html = response.text
    soup = BeautifulSoup(html, 'html.parser')
    trendings = {}
    
    # 修正CSS选择器，适应GitHub页面结构
    for article in soup.select('article.Box-row'):
        repo_info = {}
        try:
            # 提取仓库名称和URL
            h2_element = article.select_one('h2')
            if h2_element and h2_element.select_one('a'):
                name_element = h2_element.select_one('a')
                name = re.sub("\\s+", "", name_element.text).strip()
                repo_info['url'] = f"https://github.com{name_element['href'].strip()}"
                
                # 提取star数量
                star_elements = article.select('a.Link--muted')
                if len(star_elements) > 0:
                    repo_info['stars'] = star_elements[0].text.strip()
                    
                    # 提取今日新增star数量
                    today_stars_element = article.select_one('span.d-inline-block.float-sm-right')
                    repo_info['today_stars'] = re.sub(r"[^\\d]", "", today_stars_element.text) if today_stars_element else None
                
                trendings[name] = repo_info
        except Exception as e:
            print(f"Error processing repository: {e}")
    
    return trendings

def get_repo_readme(repo_url: str) -> str:
    """
    根据仓库 URL 获取 README 原始内容
    输入示例: https://github.com/punkpeye/awesome-mcp-servers
    返回 README 的 Markdown 文本内容
    """
    parts = repo_url.rstrip("/").split("/")
    if len(parts) < 2:
        return "[无效的仓库URL]"
        
    owner, repo = parts[-2], parts[-1]
    api_url = f"https://api.github.com/repos/{owner}/{repo}/readme"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "readme-fetcher"
    }
    
    # 使用带重试策略的会话
    retry_strategy = Retry(
        total=3,
        status_forcelist=[500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    http = requests.Session()
    http.mount("https://", adapter)
    
    try:
        response = http.get(api_url, headers=headers)
        response.raise_for_status()
    except RequestException as e:
        return f"[获取失败: {e}]"
    
    data = response.json()
    content_base64 = data.get("content", "")
    
    if content_base64:
        try:
            readme_text = base64.b64decode(content_base64).decode("utf-8")
            return readme_text
        except Exception as e:
            return f"[解码失败: {e}]"
    else:
        return "[该仓库没有README文件]"

def summarize_readme(repo_url: str):
    """ 将 readme 中的内容精简为仓库的 Description, 同时判断是否符合我们需求的主题
    返回类似：{'description': 'ChatTTS 是一个……。', 'is_ai': 'True'}
    """
    readme_content = get_repo_readme(repo_url)
    # 限制内容长度，避免超出LLM的最大token限制
    if len(readme_content) > 4000:
        readme_content = readme_content[:4000] + "..."
    prompt = FILTER_PROMPT.format(README_CONTENT=readme_content)
    
    response = llm.invoke([{"role": "user", "content": prompt}])
    response_dict = parse_llm_json_response(response)
    #print(response_dict)
    return response_dict

@mcp.tool()
def polish_trending_repos():
    """对爬取到的 trending 数据做进一步精简，包括过滤非 AI 内容，增加描述丰富度，最终返回优化后的字典"""
    date = datetime.date.today().strftime("%Y-%m-%d")
    trendings = get_github_trending()
    print(f"获取到 {len(trendings)} 个趋势仓库")
    filtered_trendings = {}
    
    # 创建保存结果的目录
    os.makedirs("filtered_trendings", exist_ok=True)
    
    # 设置一个进度条方便看处理哪个库
    with tqdm(total=len(trendings), desc="Processing Repositories") as pbar:
        for name, repo_info in trendings.items():
            pbar.set_description(f"Processing {name}")

            summarized_json = summarize_readme(repo_info["url"])
            
            # 检查返回结果是否包含必要的键
            if "is_ai" in summarized_json and "description" in summarized_json:
                if str(summarized_json["is_ai"]).lower() == "true":
                    filtered_trendings[name] = repo_info
                    filtered_trendings[name]["description"] = summarized_json["description"]
                    print(f"已添加 {name}: {summarized_json['description'][:50]}...")
                    
                    # 每次迭代保存一次
                    with open(f"filtered_trendings/trendings_{date}.json", "w", encoding="utf-8") as f:
                        json.dump(filtered_trendings, f, indent=2, ensure_ascii=False)
                else:
                    print(f"Skipped {name} because it is not AI related")
            else:
                print(f"Skipped {name} due to incomplete response: {summarized_json}")

            pbar.update(1)
    
    print(f"完成处理，共找到 {len(filtered_trendings)} 个AI相关仓库")
    return filtered_trendings

TEMPLATE_PROMPT = '''
# Profile
你是一个相关的Github Trending信息整理师，旨在为用户提供精炼的每周Trending仓库的信息和亮点

# Context
以下是Github Trending的信息：
{trendings}

# Workflow
1. 首先用80字左右总结Trending中的综合信息（和AI相关的），帮助读者一下了解这周的Trending态势
2. 对每个仓库，在最后包含2<=label<=4个的标签，标签需要和仓库内容高度相关，让用户可以一眼看出仓库的特点。
标签语法为<text_tag color='red'>标签文本</text_tag>,支持color参考Constraints部分，标签之间不用换行。
3. description直接复制# Context 中对应description键的信息，不要再过多精简
4. 最后需要输出JSON格式，参考如下：
输出的字典仅有`summary`和`repos`两个键，`summary`为总结，`repo`为仓库列表，每个元素为一个仅含description键的字典（**不要包括其他键！**）
注意star描述后需要换行一次，列标签需要另起一行
```json
{{"summary": "你的总结",
"repos": [
{{"description": "[CopilotKit](https://github.com/CopilotKit/CopilotKit) ⭐Total Star:1111 ⭐Today's Star：2222 
…对应的description原内容 
<text_tag color='red'>智能体</text_tag><text_tag color='orange'>RAG</text_tag>"}}, 
{{"description": "…"}},
…],
}}
```

# Constraints
1. 若要输出Markdown，只能使用如下的子集来美化你的输出，不能使用在此之外的语法例如标题#、引用>等：
换行:\n 
加粗:**粗体**
可点击的文字链接:[开放平台](https://…) 无
标签:<text_tag color='red'>标签文本</text_tag> 
其中`color`支持的枚举值范围包括如下：
- neutral: 中性色
- blue: 蓝色
- turquoise: 青绿色
- lime: 酸橙色
- orange: 橙色
- violet: 紫罗兰色
- indigo: 靛青色
- wathet: 天蓝色
- green: 绿色
- yellow: 黄色
- red: 红色
- purple: 紫色
- carmine: 洋红色

有序列表:
1. 有序列表1 
    1. 有序列表 1.1 
2. 有序列表2
要求:
- 序号需在行首使用
- 4 个空格代表一层缩进

无序列表: 要求同有序列表
2. 相同名称的标签应有相同的颜色
3. 输出中文，不要输出纯英文
'''

def generate_feishu_card():
    """根据trendings字典生成飞书卡片"""
    date = datetime.date.today().strftime("%Y-%m-%d")
    trending_path = f'filtered_trendings/trendings_{date}.json'
    template_path = f"filtered_trendings/template_{date}.json"
    with open(trending_path, 'r') as f:
        trending_repos = json.load(f)
    if not os.path.exists(trending_path):
        raise FileNotFoundError(f"trending文件{trending_path}不存在，请先运行polish_trending_repos()")

    print("正在生成推送json……")

    template_prompt = TEMPLATE_PROMPT.format(trendings=trending_repos)
    model = llm
    # print(template_prompt)
    response = model.invoke([{"role": "user", "content": template_prompt}])
    # print(response)
    template_variables = parse_llm_json_response(response)
    with open(template_path, 'w') as f:
        json.dump(template_variables, f, indent=2, ensure_ascii=False)
    print("推送json生成成功！,保存到", template_path)
@mcp.tool()
def send_to_feishu():
    """
    将格式化的消息用消息卡片模板推送到飞书
    飞书卡片工具参考：<https://open.feishu.cn/document/uAjLw4CM/ukzMukzMukzM/feishu-cards/feishu-card-cardkit/feishu-cardkit-overview>
    """
    date = datetime.date.today().strftime("%Y-%m-%d")
    template_path = f"filtered_trendings/template_{date}.json"
    if not os.path.exists(template_path):
        generate_feishu_card()
    with open(template_path, 'r') as f:
        template_variable = json.load(f)
    FEISHU_WEB_HOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/xxxx"
    body = json.dumps(
        {
            "msg_type": "interactive",
            "card": {
                "type": "template",
                "data": {
                    "template_id": "xxxxx",
                    "template_version_name": "1.0.0",  # 需要版本对应
                    "template_variable": template_variable
                }
            }
        })
    response = requests.post(FEISHU_WEB_HOOK, data=body)
    print(response.text)
    
if __name__ == "__main__":
    print("MCP SERVICER服务已启动...")
    mcp.run(transport='stdio')   