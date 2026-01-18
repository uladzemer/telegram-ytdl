type MergeCookieResult = {
	content: string
	addedCookies: number
	totalCookies: number
	incomingCookieLines: number
	invalidIncoming: number
}

const isValidCookieLine = (line: string) => line.split("\t").length >= 7

export const mergeCookieContent = (
	existing: string,
	incoming: string,
): MergeCookieResult => {
	const headerLines: string[] = []
	const cookieLines: string[] = []
	const headerSet = new Set<string>()
	const cookieSet = new Set<string>()
	let invalidIncoming = 0
	let incomingCookieLines = 0
	let addedCookies = 0

	const addLines = (content: string, countIncoming: boolean) => {
		for (const line of content.split(/\r?\n/)) {
			const trimmed = line.trim()
			if (!trimmed) continue
			if (trimmed.startsWith("#")) {
				if (!headerSet.has(trimmed)) {
					headerSet.add(trimmed)
					headerLines.push(trimmed)
				}
				continue
			}
			if (countIncoming) {
				incomingCookieLines += 1
				if (!isValidCookieLine(trimmed)) {
					invalidIncoming += 1
				}
			}
			if (!cookieSet.has(trimmed)) {
				cookieSet.add(trimmed)
				cookieLines.push(trimmed)
				if (countIncoming) {
					addedCookies += 1
				}
			}
		}
	}

	addLines(existing, false)
	addLines(incoming, true)

	if (headerLines.length === 0) {
		headerLines.push("# Netscape HTTP Cookie File")
	}

	const merged = [...headerLines, "", ...cookieLines].join("\n").trimEnd()
	return {
		content: `${merged}\n`,
		addedCookies,
		totalCookies: cookieLines.length,
		incomingCookieLines,
		invalidIncoming,
	}
}

export const cookieFormatExample =
	".example.com\tTRUE\t/\tFALSE\t1716239021\tsessionid\tabc123"
