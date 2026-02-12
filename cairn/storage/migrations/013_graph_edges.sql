-- Migration 013: Graph edge weights and PageRank for spreading activation
-- Adds edge_weight to memory_relations for weighted graph traversal.
-- Adds pagerank to memories for structural importance scoring.

ALTER TABLE memory_relations ADD COLUMN IF NOT EXISTS edge_weight FLOAT DEFAULT 1.0;

ALTER TABLE memories ADD COLUMN IF NOT EXISTS pagerank FLOAT DEFAULT 0.0;
