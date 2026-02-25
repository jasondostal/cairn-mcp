"""Tests for HCL language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_HCL = '''# AWS region configuration
variable "aws_region" {
  description = "The AWS region"
  type        = string
  default     = "us-east-1"
}

# Main VPC resource
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

# AMI data source
data "aws_ami" "ubuntu" {
  most_recent = true
}

# VPC ID output
output "vpc_id" {
  value = aws_vpc.main.id
}

module "networking" {
  source = "./modules/networking"
}

locals {
  env = "production"
}
'''


class TestHclParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_HCL, "hcl")
        assert result.ok
        assert result.language == "hcl"
        assert len(result.content_hash) == 64

    def test_variable_block_extracted(self):
        result = self.parser.parse_source(SAMPLE_HCL, "hcl")
        variables = [s for s in result.symbols if s.kind == "variable"]
        assert len(variables) == 1
        assert variables[0].name == "aws_region"

    def test_resource_block_extracted(self):
        result = self.parser.parse_source(SAMPLE_HCL, "hcl")
        resources = [s for s in result.symbols if s.kind == "resource"]
        assert len(resources) == 1
        assert resources[0].name == "aws_vpc.main"

    def test_data_block_extracted(self):
        result = self.parser.parse_source(SAMPLE_HCL, "hcl")
        data_blocks = [s for s in result.symbols if s.kind == "data"]
        assert len(data_blocks) == 1
        assert data_blocks[0].name == "aws_ami.ubuntu"

    def test_output_block_extracted(self):
        result = self.parser.parse_source(SAMPLE_HCL, "hcl")
        outputs = [s for s in result.symbols if s.kind == "output"]
        assert len(outputs) == 1
        assert outputs[0].name == "vpc_id"

    def test_module_block_extracted(self):
        result = self.parser.parse_source(SAMPLE_HCL, "hcl")
        modules = [s for s in result.symbols if s.kind == "module"]
        assert len(modules) == 1
        assert modules[0].name == "networking"

    def test_locals_block_extracted(self):
        result = self.parser.parse_source(SAMPLE_HCL, "hcl")
        locals_blocks = [s for s in result.symbols if s.kind == "locals"]
        assert len(locals_blocks) == 1
        assert locals_blocks[0].name == "locals"

    def test_resource_signature(self):
        result = self.parser.parse_source(SAMPLE_HCL, "hcl")
        vpc = next(s for s in result.symbols if s.kind == "resource")
        assert vpc.signature == 'resource "aws_vpc" "main"'

    def test_data_signature(self):
        result = self.parser.parse_source(SAMPLE_HCL, "hcl")
        ami = next(s for s in result.symbols if s.kind == "data")
        assert ami.signature == 'data "aws_ami" "ubuntu"'

    def test_variable_signature(self):
        result = self.parser.parse_source(SAMPLE_HCL, "hcl")
        var = next(s for s in result.symbols if s.kind == "variable")
        assert var.signature == 'variable "aws_region"'

    def test_doc_comments(self):
        result = self.parser.parse_source(SAMPLE_HCL, "hcl")
        var = next(s for s in result.symbols if s.kind == "variable")
        assert var.docstring == "AWS region configuration"

    def test_resource_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_HCL, "hcl")
        vpc = next(s for s in result.symbols if s.kind == "resource")
        assert vpc.docstring == "Main VPC resource"

    def test_data_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_HCL, "hcl")
        ami = next(s for s in result.symbols if s.kind == "data")
        assert ami.docstring == "AMI data source"

    def test_output_doc_comment(self):
        result = self.parser.parse_source(SAMPLE_HCL, "hcl")
        output = next(s for s in result.symbols if s.kind == "output")
        assert output.docstring == "VPC ID output"

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_HCL, "hcl")
        vpc = next(s for s in result.symbols if s.kind == "resource")
        assert vpc.start_line > 0
        assert vpc.end_line >= vpc.start_line

    def test_symbol_kinds(self):
        result = self.parser.parse_source(SAMPLE_HCL, "hcl")
        kinds = {s.kind for s in result.symbols}
        assert "variable" in kinds
        assert "resource" in kinds
        assert "data" in kinds
        assert "output" in kinds
        assert "module" in kinds
        assert "locals" in kinds

    def test_empty_file(self):
        result = self.parser.parse_source("# empty\n", "hcl")
        assert result.ok
        assert len(result.symbols) == 0

    def test_resource_qualified_name(self):
        result = self.parser.parse_source(SAMPLE_HCL, "hcl")
        vpc = next(s for s in result.symbols if s.kind == "resource")
        assert vpc.qualified_name == "aws_vpc.main"

    def test_multiple_resources(self):
        source = '''
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "public" {
  vpc_id = aws_vpc.main.id
}
'''
        result = self.parser.parse_source(source, "hcl")
        resources = [s for s in result.symbols if s.kind == "resource"]
        assert len(resources) == 2
        names = {r.name for r in resources}
        assert "aws_vpc.main" in names
        assert "aws_subnet.public" in names
