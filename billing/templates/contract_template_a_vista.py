contract_template = """
CONTRATO DE CONFISSÃO E RENEGOCIAÇÃO DE DÍVIDAS

{{ debtor_name }}, inscrita no CPF/MF sob o nº {{ debtor_cpf }}, residente e domiciliada na 
{{ debtor_address }}, no bairro {{ debtor_neighborhood }}, CEP {{ debtor_cep }}, no Município de {{ debtor_city }}, no Estado do {{ debtor_state }}, possuidor
do Whatsapp {{ debtor_whatsapp }}, doravante denominado 
DEVEDOR e 

{{ credor_name }}, organização jurídica de direito privado, inscrita no 
CNPJ sob o nº {{ credor_cnpj }}, com sede na {{ credor_address }}, 
no bairro {{ credor_neighborhood }}, CEP {{ credor_cep }}, no Município de {{ credor_city }}, no Estado do 
{{ credor_state }}, possuidor do e-mail {{ credor_email }}, neste ato representado pela 
Síndica em exercício eleita em Assembleia Geral Ordinária no dia {{ sindico_election_date }}, Sra. 
{{ sindico_name }}, {{ sindico_profession }}, inscrita no CPF/MF sob 
o nº {{ sindico_cpf }}, residente e domiciliada na {{ sindico_address }}, 
no bairro {{ sindico_neighborhood }}, CEP {{ sindico_cep }}, no Município de {{ sindico_city }}, 
no Estado do {{ sindico_state }}, doravante denominado CREDOR

As partes acima qualificadas de livre e espontânea vontade celebram entre si o presente 
contrato particular de confissão e renegociação de dívidas que regerá pelos seguintes 
termos:

DO OBJETO
CLÁUSULA PRIMEIRA – O DEVEDOR reconhece, confessa e declara que deve ao CREDOR a 
quantia líquida e certa de R$ {{ debt_amount }} ({{ debt_amount_words }}), referente as taxas condominiais, provisão para 13º terceiro, salário e 
INSS, fundo de reserva, bem como demais despesas aprovadas em assembleia vencidas 
no período de: {{ debt_periods }}, em conformidade com o cálculo 
em anexo encaminhado pela contabilidade, o qual integra o presente contrato.  

PARÁGRAFO PRIMEIRO – Em razão do atraso e da necessidade de contratação do setor 
jurídico para resolução da situação, o DEVEDOR reconhece, confessa e declara que deve 
a importância de 10% (dez) por cento do valor da dívida à assessoria jurídica contratada, 
conforme autorização prevista na cláusula 41 da Convenção do Condomínio.

PARÁGRAFO SEGUNDO – Portanto, o DEVEDOR assume total responsabilidade pelo 
adimplemento das obrigações previstas na CLÁUSULA PRIMEIRA e PARÁGRAFO 
PRIMEIRO acima, obrigando-se a pagar a dívida confessada, ou seja, a importância de R$ 
{{ total_debt }} ({{ total_debt_words }}).

DO PAGAMENTO

CLÁUSULA SEGUNDA – Para o adimplemento dos valores confessados o DEVEDOR se 
compromete ao pagamento da seguinte forma, o montante de R$ {{ total_debt }} ({{ total_debt_words }}) em uma parcela única no valor de R$ {{ total_debt }} ({{ total_debt_words }}) 
a vencer no dia {{ due_date }}, 

PARÁGRAFO PRIMEIRO – Para o pagamento será enviado, na data da assinatura do 
presente acordo, o boleto gerado pela contabilidade por meio de aplicativo de 
mensagem instantânea whatsapp e email.  

PARÁGRAFO SEGUNDO – O comprovante de pagamento serve como recibo de quitação.

DO INADIMPLEMENTO

CLÁUSULA TERCEIRA – No caso do não pagamento do boleto na data de vencimento, 
incidirá sobre o valor previsto no PARÁGRAFO SEGUNDO da CLÁUSULA PRIMEIRA multa 
de 2% (dois por cento) e juros de mora de 1% (um por cento) ao mês, além de correção 
monetária pelo índice IGP-M, excluindo-se eventual índice negativo, de acordo com o 
aprovado em assembleia do dia {{ assembly_date }}, mais custas processuais e honorários 
advocatícios no caso de ajuizamento de ação, além de cláusula penal de 20% (vinte por 
cento) calculado sobre o valor total do débito, sem prejuízo da indenização por 
eventuais perdas e danos adicionais.  

PARÁGRAFO PRIMEIRO – O DEVEDOR autoriza o CREDOR a efetuar a inclusão do seu 
nome junto aos cadastros de inadimplentes, tais como SPC, SERASA e outros.

PARÁGRAFO SEGUNDO – Eventual pagamento do boleto fora do prazo previsto na 
CLÁUSULA SEGUNDA ou a menor servirá apenas como pagamento parcial da dívida e 
acarretará o vencimento antecipado da dívida, nos termos do parágrafo seguinte.

PARÁGRAFO TERCEIRO – A dívida ora confessada vencerá automática e 
antecipadamente, de pleno direito, independentemente de notificação ou interpelação 
judicial ou extrajudicial, para desde logo tornar-se exigível, inclusive, os seus acessórios, 
se o pagamento do débito não for pago na forma e no prazo previsto 
neste Instrumento.

PARÁGRAFO QUARTO – A eventual tolerância à infringência, reiterada ou não, a 
qualquer cláusula contratual não ensejará em renúncia ou modificação tácita do 
ajustado no presente acordo, mas mera liberdade, não implicando em novação ou 
transação de qualquer espécie.

DISPOSIÇÕES GERAIS

CLÁUSULA QUARTA – O presente Contrato e seus Anexos constituem o inteiro e total 
acordo entre as partes e somente poderão ser alterados mediante contrato escrito 
assinado pelas partes.

CLÁUSULA QUINTA – Eventuais e-mails, mensagens de Whatsapp e toda a comunicação 
anterior estabelecida entre as partes encontra-se consolidada neste contrato e reflete o 
consenso a que chegaram após ampla negociação e concessões recíprocas e, por essa 
razão, a comunicação referida não pode ser utilizada para interpretar ou integrar o 
presente instrumento, sob pena de ser violada a autonomia das partes.

CLÁUSULA SEXTA – As partes declaram e reconhecem que o presente contrato supera e 
substitui todo e qualquer outro acordo oral ou por escrito celebrado entre as partes.

CLÁUSULA SÉTIMA – A confissão de dívida constante deste contrato é definitiva e 
irretratável, não implicando, de modo algum, novação ou transação e vigorará 
imediatamente, obrigando-se as partes por si, seus herdeiros e sucessores.

CLÁUSULA OITAVA – O DEVEDOR declara ciente que ao confessar e assinar o presente 
acordo, as dívidas confessadas no CAPUT e PARÁGRAFO PRIMEIRO da CLÁUSULA 
PRIMEIRA passam a ser líquida, certa e exigível, nos termos do art. 784, inciso III, do 
Código de Processo Civil, passível de execução, expropriação de bens móveis e imóveis 
em caso de não pagamento.

CLÁUSULA NONA – As partes acordam, desde já, que são válidas as notificações e 
comunicações realizadas nos endereços indicados no preâmbulo do presente contrato, 
inclusive os endereços eletrônicos e aplicativos de mensagens instantâneas.

CLÁUSULA DÉCIMA – O CREDOR poderá a qualquer tempo, independentemente de 
notificação ao DEVEDOR ceder o crédito decorrente deste contrato.

CLÁUSULA DÉCIMA PRIMEIRA – Para dirimir quaisquer dúvidas oriundas do presente 
contrato, as partes elegem o Foro da Comarca de {{ forum_city }}, Estado do {{ forum_state }}.

CLÁUSULA DÉCIMA SEGUNDA – As partes, inclusive suas testemunhas, reconhecem a 
forma de contratação por meios eletrônicos, digitais e informáticos como válida e 
plenamente eficaz, ainda que seja estabelecida sem certificação de padrão IPC – BRASIL, 
conforme disposto pelo art. 10 da Medida Provisória nº 2.200/2001 em vigor no Brasil.

{{ city }}, {{ current_date }}.

{{ debtor_name }}     {{ credor_name }}

Testemunhas:

{{ witness_name }}

CPF: {{ witness_cpf }}  
E-MAIL: {{ witness_email }}
"""