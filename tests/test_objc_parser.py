"""Tests for Objective-C language support in the tree-sitter code parser."""

from cairn.code.parser import CodeParser


SAMPLE_OBJC = '''#import <Foundation/Foundation.h>
#import "MyHeader.h"

@protocol MyProtocol
- (void)doSomething;
@end

@interface MyClass : NSObject <MyProtocol>
@property (nonatomic, strong) NSString *name;
- (void)doSomething;
+ (instancetype)sharedInstance;
@end

@implementation MyClass
- (void)doSomething {
    NSLog(@"Hello");
}
+ (instancetype)sharedInstance {
    static MyClass *instance = nil;
    return instance;
}
@end
'''


class TestObjcParser:

    def setup_method(self):
        self.parser = CodeParser()

    def test_parse_source_basic(self):
        result = self.parser.parse_source(SAMPLE_OBJC, "objc")
        assert result.ok
        assert result.language == "objc"
        assert len(result.content_hash) == 64

    def test_imports_extracted(self):
        result = self.parser.parse_source(SAMPLE_OBJC, "objc")
        imports = {s.name for s in result.imports}
        assert "<Foundation/Foundation.h>" in imports
        assert "MyHeader.h" in imports

    def test_protocol_extracted(self):
        result = self.parser.parse_source(SAMPLE_OBJC, "objc")
        protocols = [s for s in result.symbols if s.kind == "protocol"]
        assert len(protocols) == 1
        assert protocols[0].name == "MyProtocol"

    def test_class_extracted(self):
        result = self.parser.parse_source(SAMPLE_OBJC, "objc")
        classes = [s for s in result.symbols if s.kind == "class"]
        assert len(classes) == 1
        assert classes[0].name == "MyClass"

    def test_methods_extracted(self):
        result = self.parser.parse_source(SAMPLE_OBJC, "objc")
        methods = [s for s in result.symbols if s.kind == "method"]
        names = {s.name for s in methods}
        assert "doSomething" in names

    def test_property_extracted(self):
        result = self.parser.parse_source(SAMPLE_OBJC, "objc")
        props = [s for s in result.symbols if s.kind == "property"]
        assert len(props) >= 1
        names = {s.name for s in props}
        assert "name" in names

    def test_method_parent(self):
        result = self.parser.parse_source(SAMPLE_OBJC, "objc")
        methods = [s for s in result.symbols if s.kind == "method" and s.parent_name]
        parent_names = {s.parent_name for s in methods}
        assert "MyClass" in parent_names or "MyProtocol" in parent_names

    def test_protocol_signature(self):
        result = self.parser.parse_source(SAMPLE_OBJC, "objc")
        proto = next(s for s in result.symbols if s.kind == "protocol")
        assert "@protocol" in proto.signature

    def test_line_numbers(self):
        result = self.parser.parse_source(SAMPLE_OBJC, "objc")
        cls = next(s for s in result.symbols if s.kind == "class")
        assert cls.start_line > 0
        assert cls.end_line >= cls.start_line

    def test_empty_file(self):
        result = self.parser.parse_source("", "objc")
        assert result.ok
        assert len(result.symbols) == 0

    def test_import_signature(self):
        result = self.parser.parse_source(SAMPLE_OBJC, "objc")
        imp = next(s for s in result.imports if "Foundation" in s.name)
        assert "#import" in imp.signature
