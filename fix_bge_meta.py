"""补齐 sentence-transformers 加载 bge 所需的 3 个配置文件（本地手写，不需要网络）。"""
import json
from pathlib import Path

try:  # 目录从 kb_vector 统一取
    import kb_vector as _KV
    D = _KV.BASE / "models" / "bge-small-zh-v1.5"
except Exception:
    D = Path(r"G:\kb-vector\models\bge-small-zh-v1.5")

MODULES = [
    {
        "idx": 0,
        "name": "0",
        "path": "",
        "type": "sentence_transformers.models.Transformer",
    },
    {
        "idx": 1,
        "name": "1",
        "path": "1_Pooling",
        "type": "sentence_transformers.models.Pooling",
    },
]
BERT = {"max_seq_length": 512, "do_lower_case": False}

# Tokenizer 配置：bge-zh 用 BERT 中文词表（整体词表，不分词）
TOK_CFG = {
    "do_lower_case": False,
    "do_basic_tokenize": True,
    "never_split": None,
    "tokenize_chinese_chars": True,
    "strip_accents": None,
    "model_max_length": 512,
    "tokenizer_class": "BertTokenizer",
    "clean_up_tokenization_spaces": True,
}

# config.json：bge-small-zh-v1.5 是 4 层 512 隐藏维度的 BERT
CFG = {
    "architectures": ["BertModel"],
    "attention_probs_dropout_prob": 0.1,
    "classifier_dropout": None,
    "hidden_act": "gelu",
    "hidden_dropout_prob": 0.1,
    "hidden_size": 512,
    "initializer_range": 0.02,
    "intermediate_size": 2048,
    "layer_norm_eps": 1e-12,
    "max_position_embeddings": 512,
    "model_type": "bert",
    "num_attention_heads": 8,
    "num_hidden_layers": 4,
    "pad_token_id": 0,
    "position_embedding_type": "absolute",
    "torch_dtype": "float32",
    "transformers_version": "4.30.0",
    "type_vocab_size": 2,
    "use_cache": True,
    "vocab_size": 21128,
}


def main():
    (D / "modules.json").write_text(json.dumps(MODULES, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
    (D / "sentence_bert_config.json").write_text(json.dumps(BERT, indent=2), encoding="utf-8")
    (D / "tokenizer_config.json").write_text(json.dumps(TOK_CFG, indent=2), encoding="utf-8")
    (D / "1_Pooling").mkdir(exist_ok=True)
    (D / "1_Pooling" / "config.json").write_text(
        json.dumps({"word_embedding_dimension": 512,
                    "pooling_mode_cls_token": False,
                    "pooling_mode_mean_tokens": True,
                    "pooling_mode_max_tokens": False,
                    "pooling_mode_mean_sqrt_len_tokens": False}, indent=2),
        encoding="utf-8")
    # 已知 config.json 若被截断就重写
    cur = (D / "config.json")
    if not cur.exists() or cur.stat().st_size < 200:
        cur.write_text(json.dumps(CFG, indent=2), encoding="utf-8")
    print("写好：", [p.name for p in sorted(D.rglob("*")) if p.is_file()])


if __name__ == "__main__":
    main()