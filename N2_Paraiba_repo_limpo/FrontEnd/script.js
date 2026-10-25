const pdfInput =
    document.getElementById("pdfInput");

const selectFileButton =
    document.getElementById("selectFileButton");

const fileName =
    document.getElementById("fileName");

const selectedFile =
    document.getElementById("selectedFile");

const selectedFileName =
    document.getElementById("selectedFileName");

const selectedFileSize =
    document.getElementById("selectedFileSize");

const removeFileButton =
    document.getElementById("removeFileButton");

const extractButton =
    document.getElementById("extractButton");

const resultSection =
    document.getElementById("resultSection");

const jsonResult =
    document.getElementById("jsonResult");

const copyButton =
    document.getElementById("copyButton");


/* =========================================
   ENDEREÇO DA API
========================================= */

const API_URL =
    "http://127.0.0.1:8000";


/* =========================================
   ABRIR SELETOR DE ARQUIVOS
========================================= */

selectFileButton.addEventListener(
    "click",
    () => {

        pdfInput.click();

    }
);


/* =========================================
   ARQUIVO SELECIONADO
========================================= */

pdfInput.addEventListener(
    "change",
    () => {

        const file =
            pdfInput.files[0];


        if (!file) {

            return;

        }


        /* Verificar PDF */

        if (
            file.type !==
            "application/pdf"
        ) {

            alert(
                "Por favor, selecione um arquivo PDF."
            );

            resetFile();

            return;

        }


        fileName.textContent =
            file.name;


        selectedFileName.textContent =
            file.name;


        selectedFileSize.textContent =
            formatFileSize(
                file.size
            );


        selectedFile.classList.remove(
            "hidden"
        );


        extractButton.disabled =
            false;

    }
);


/* =========================================
   REMOVER ARQUIVO
========================================= */

removeFileButton.addEventListener(
    "click",
    () => {

        resetFile();

    }
);


/* =========================================
   EXTRAIR DADOS
========================================= */

extractButton.addEventListener(
    "click",
    async () => {

        const file =
            pdfInput.files[0];


        if (!file) {

            alert(
                "Selecione uma nota fiscal primeiro."
            );

            return;

        }


        /* Cria o formulário que enviará o PDF */

        const formData =
            new FormData();


        formData.append(
            "arquivo",
            file
        );


        /* Muda o botão enquanto processa */

        extractButton.disabled =
            true;


        extractButton.innerHTML =
            "Extraindo dados...";


        try {

            /* Envia o PDF ao FastAPI */

            const resposta =
                await fetch(
                    `${API_URL}/extrair-nota`,
                    {
                        method: "POST",
                        body: formData
                    }
                );


            /* Verifica erro HTTP */

            if (!resposta.ok) {

                const erro =
                    await resposta.json();


                throw new Error(
                    erro.detail ||
                    "Erro ao processar a nota fiscal."
                );

            }


            /* Recebe o JSON */

            const dados =
                await resposta.json();


            /* Mostra na tela */

            mostrarResultado(
                dados
            );


        } catch (erro) {

            console.error(
                "Erro:",
                erro
            );


            alert(
                "Erro ao extrair dados: " +
                erro.message
            );

        } finally {

            extractButton.disabled =
                false;


            extractButton.innerHTML =
                "<span>◉</span> EXTRAIR DADOS";

        }

    }
);


/* =========================================
   MOSTRAR JSON
========================================= */

function mostrarResultado(dados) {

    jsonResult.textContent =
        JSON.stringify(
            dados,
            null,
            4
        );


    resultSection.classList.remove(
        "hidden"
    );


    resultSection.scrollIntoView(
        {
            behavior: "smooth",
            block: "start"
        }
    );

}


/* =========================================
   COPIAR JSON
========================================= */

copyButton.addEventListener(
    "click",
    async () => {

        const json =
            jsonResult.textContent;


        try {

            await navigator.clipboard.writeText(
                json
            );


            const textoOriginal =
                copyButton.textContent;


            copyButton.textContent =
                "✓ JSON copiado";


            setTimeout(
                () => {

                    copyButton.textContent =
                        textoOriginal;

                },
                2000
            );


        } catch (erro) {

            console.error(
                "Erro ao copiar:",
                erro
            );


            alert(
                "Não foi possível copiar o JSON."
            );

        }

    }
);


/* =========================================
   LIMPAR ARQUIVO
========================================= */

function resetFile() {

    pdfInput.value =
        "";


    fileName.textContent =
        "Nenhum arquivo selecionado";


    selectedFileName.textContent =
        "";


    selectedFileSize.textContent =
        "";


    selectedFile.classList.add(
        "hidden"
    );


    resultSection.classList.add(
        "hidden"
    );


    jsonResult.textContent =
        "";


    extractButton.disabled =
        true;

}


/* =========================================
   FORMATAR TAMANHO DO ARQUIVO
========================================= */

function formatFileSize(bytes) {

    if (bytes === 0) {

        return "0 Bytes";

    }


    const unidade =
        1024;


    const tamanhos = [

        "Bytes",
        "KB",
        "MB",
        "GB"

    ];


    const indice =
        Math.floor(
            Math.log(bytes) /
            Math.log(unidade)
        );


    const tamanho =
        bytes /
        Math.pow(
            unidade,
            indice
        );


    return (
        tamanho.toFixed(2) +
        " " +
        tamanhos[indice]
    );

}