# core/genai/prompt.py
"""
プロンプトを部品(Section・TextBlock・BulletInstruction・MandatoryRule等)の組み合わせで作る。
Sectionは見出しの深さと番号(1., 1.1.)を自動で振り、Prompt.to_text()でマークダウンの文字列になる。
"""


class PromptComponent:
    def to_text(self, depth: int, index_prefix: str) -> str:
        """
        depth: 見出しの深さ（# の数）
        index_prefix: 親から引き継いだインデックス番号（例: "1.2"）
        """
        raise NotImplementedError

class Section(PromptComponent):
    """タイトルを持ち、配下の子要素のナンバリングを自動制御するセクション"""
    def __init__(self, title: str, children: list[PromptComponent] = None):
        self.title = title
        self.children = children if children is not None else []

    def to_text(self, depth: int, index_prefix: str) -> str:
        # 見出しの記号 (例: depth=1 -> "#", depth=2 -> "##")
        header_prefix = "#" * depth
        
        # インデックス番号の生成
        # 最上位(depth=1)なら "1.", 階層2なら "1.1." などの形式にする
        current_index = f"{index_prefix}." if index_prefix else ""
        
        lines = [f"{header_prefix} {current_index}{self.title}"]
        
        # 子要素のレンダリング
        # 子要素がさらに「Section」だった場合、その中での連番（1, 2, 3...）をカウントする
        section_child_count = 1
        for child in self.children:
            if isinstance(child, Section):
                # 次の階層へ渡すインデックス文字列を生成（例: 親が "1" で自身が2番目のセクションなら "1.2"）
                next_prefix = f"{index_prefix}.{section_child_count}" if index_prefix else f"{section_child_count}"
                lines.append(child.to_text(depth=depth + 1, index_prefix=next_prefix))
                section_child_count += 1
            else:
                # プレーンテキストやリストなどの末端要素は、インデックスを重ねずそのまま描画
                lines.append(child.to_text(depth=depth + 1, index_prefix=""))
            
        return "\n\n".join(lines)

class TextBlock(PromptComponent):
    def __init__(self, text: str):
        self.text = text.strip()

    def to_text(self, depth: int, index_prefix: str) -> str:
        return self.text

class BulletInstruction(PromptComponent):
    def __init__(self, items: list[str]):
        self.items = items

    def to_text(self, depth: int, index_prefix: str) -> str:
        return "\n".join([f" - {item}" for item in self.items])

class StepInstruction(PromptComponent):
    def __init__(self, steps: list[str]):
        self.steps = steps

    def to_text(self, depth: int, index_prefix: str) -> str:
        return "\n".join([f" {i}. {step}" for i, step in enumerate(self.steps, 1)])

class MandatoryRule(PromptComponent):
    """厳守事項：他の指示コンポーネントを内包するコンテナ"""
    def __init__(self, content: PromptComponent):
        self.content = content

    def to_text(self, depth: int, index_prefix: str) -> str:
        # 子コンポーネントのテキストを取得し、その前に [厳守事項] のラベルを付与する
        # （子要素のインデントを崩さないよう、ラベルの直後で改行を入れる設計が安全です）
        return f"### [厳守事項]\n{self.content.to_text(depth, index_prefix)}"

class ForbiddenRule(PromptComponent):
    """禁止事項：他の指示コンポーネントを内包するコンテナ"""
    def __init__(self, content: PromptComponent):
        self.content = content

    def to_text(self, depth: int, index_prefix: str) -> str:
        return f"### [禁止事項]\n{self.content.to_text(depth, index_prefix)}"

class OutputFormat(PromptComponent):
    def __init__(self, format_type: str, template: str):
        self.format_type = format_type.lower()
        self.template = template.strip()

    def to_text(self, depth: int, index_prefix: str) -> str:
        return f"### [出力仕様]\n{self.template}\n"

class Prompt:
    def __init__(self, components: list[PromptComponent] = None):
        self.components = components if components is not None else []

    def to_text(self) -> str:
        results = []
        # 最上位セクションのカウンター
        top_section_count = 1
        for comp in self.components:
            if isinstance(comp, Section):
                # ルート要素はインデックス "1", "2", "3"... からスタート
                results.append(comp.to_text(depth=1, index_prefix=str(top_section_count)))
                top_section_count += 1
            else:
                results.append(comp.to_text(depth=1, index_prefix=""))
                
        return "\n\n\n".join(results)

    def __str__(self) -> str:
        return self.to_text()