from schema_miner.core.schema_mining import SchemaMiner
from schema_miner.core.config import load_config

config = load_config("config.yaml")
miner = SchemaMiner(config)
miner.run()
