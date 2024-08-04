var HttpErrorCodes = require("./const.js").HttpErrorCodes;

var items = [
    ['en', 'en']
];

var langMap = new Map(items);
var langMapReverse = new Map(items.map(([standardLang, lang]) => [lang, standardLang]));

function supportLanguages() {
    return items.map(([standardLang, lang]) => standardLang);
}

function tts(query, completion) {

    const { api_path } = $option;

    const body = {
        query: query.text
    };

    (async () => {
        const response = await $http.request(
            {
                method: "GET",
                url: api_path,
                body: body,
            }
        );

        if (response.error) {
            const { statusCode } = response.response;
            const reason = (statusCode >= 400 && statusCode < 500) ? "param" : "api";
            completion(
                {
                    error: {
                        type: reason,
                        message: `接口响应错误 - ${HttpErrorCodes[statusCode]}`,
                        addition: `${JSON.stringify(response)}`,
                    },
                }
            )
        } else {
            completion(
                {
                    result: {
                        type: "base64",
                        value: response.rawData.toBase64()
                    }
                }
            )
        }
    })().catch((err) => {
        if ('response' in err) {
            const { statusCode } = err.response;
            const reason = (statusCode >= 400 && statusCode < 500) ? "param" : "api";
            completion(
                {
                    error: {
                        type: reason,
                        message: `接口响应错误 - ${HttpErrorCodes[statusCode]}`,
                        addition: `${JSON.stringify(err)}`,
                    },
                }
            )
        } else {
            completion(
                {
                    error: {
                        ...err,
                        type: err.type || "unknown",
                        message: err.message || "Unknown error",
                    },
                }
            )
        }
    });
}

function pluginTimeoutInterval() {
    return 20;
}

exports.supportLanguages = supportLanguages;
exports.tts = tts;