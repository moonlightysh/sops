(function () {
    $.atoms.my_http_check = [
        {
                "tag_code": "url",
                "type": "input",
                "attrs": {
                        "name": "Target URL",
                        "hookable": true
                }
        },
        {
                "tag_code": "method",
                "type": "input",
                "attrs": {
                        "name": "Method(默认GET)",
                        "hookable": true
                }
        },
        {
                "tag_code": "timeout",
                "type": "int",
                "attrs": {
                        "name": "Timeout (s)(默认10)",
                        "hookable": true
                }
        },
        {
                "tag_code": "expect_status",
                "type": "int",
                "attrs": {
                        "name": "Expected status(默认200)",
                        "hookable": true
                }
        },
        {
                "tag_code": "keyword",
                "type": "input",
                "attrs": {
                        "name": "Keyword(可选)",
                        "hookable": true
                }
        },
    ]
})();
