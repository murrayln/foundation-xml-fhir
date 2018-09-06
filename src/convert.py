#!/usr/bin/env python
import argparse
import base64
import json
import logging
import uuid
import xmltodict
import os
import gzip
import shutil
import datetime
from utils import parse_hgvs
from subprocess import call


logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s')
logger = logging.getLogger(__name__)


def read_xml(xml_file):
    with open(xml_file) as fd:
        return xmltodict.parse(fd.read())


def save_json(fhir_resources, out_file):
    with open(out_file, 'wb') as fd:
        json.dump(fhir_resources, fd, indent=4)


def unzip(zipped_file):
    unzipped_file = os.path.splitext(zipped_file)[0]
    logger.info('Unzipping %s to %s', zipped_file, unzipped_file)

    with gzip.open(zipped_file, "rb") as f_in, open(unzipped_file, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)

    logger.info('Unzipping completed')
    return unzipped_file


def create_copy_number_observation(project_id, subject_id, specimen_id, specimen_name, sequence_id):
    def create(variant_dict):
        observation_id = str(uuid.uuid4())
        position_value = variant_dict['@position']
        region, position = position_value.split(':')

        observation = {
            'resourceType': 'Observation',
            'meta': {
                'tag': [
                    {
                        'system': 'http://lifeomic.com/fhir/dataset',
                        'code': project_id
                    },
                    {
                        'system': 'http://lifeomic.com/fhir/source',
                        'code': 'LifeOmic Task Service'
                    }
                ]
            },
            'code': {
                'coding': [
                {
                    'system': 'http://loinc.org',
                    'code': '55233-1',
                    'display': 'Genetic analysis master panel-- This is the parent OBR for the panel holding all of the associated observations that can be reported with a molecular genetics analysis result.'
                }
                ]
            },
            'status': 'final',
            'subject': {
                'reference': 'Patient/{}'.format(subject_id)
            },
            'specimen': {
                'display': specimen_name,
                'reference': 'Specimen/{}'.format(specimen_id)
            },
            'valueCodeableConcept': {
                'coding': [
                    {
                    'system': 'http://foundationmedicine.com',
                    'code': variant_dict['@status'],
                    'display': 'Foundation - {}'.format(variant_dict['@status'].title())
                    }
                ]
            },
            'extension': [
                {
                    'url': 'http://hl7.org/fhir/StructureDefinition/observation-geneticsGene',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://www.genenames.org',
                                'code': '1100',
                                'display': variant_dict['@gene']
                            }
                        ]
                    }
                },
                {
                    'url': 'http://hl7.org/fhir/StructureDefinition/observation-geneticsDNASequenceVariantName',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://loinc.org',
                                'code': '48004-6',
                                'display': '{}: CN={}'.format(variant_dict['@type'].title(), variant_dict['@copy-number'])
                            }
                        ]
                    }
                },
                {
                    'url': 'http://hl7.org/fhir/StructureDefinition/observation-geneticsGenomicSourceClass',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://loinc.org',
                                'code': '48002-0',
                                'display': 'somatic'
                            }
                        ]
                    }
                },
                {
                    'url': 'http://hl7.org/fhir/StructureDefinition/observation-geneticsSequence',
                    'valueReference': {
                        'reference': 'Sequence/{}'.format(sequence_id)
                    }
                },
                {
                    'url': 'http://lifeomic.com/fhir/StructureDefinition/observation-geneticsDNAPosition',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://loinc.org',
                                'code': '48001-2',
                                'display': position
                            }
                        ]
                    }
                },
                {
                    'url': 'http://lifeomic.com/fhir/StructureDefinition/observation-geneticsDNAChromosome',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://loinc.org',
                                'code': '47999-8',
                                'display': region
                            }
                        ]
                    }
                },
                {
                    'url': 'http://hl7.org/fhir/StructureDefinition/observation-geneticsCopyNumberEvent',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://www.sequenceontology.org',
                                'code': 'SO:0001019',
                                'display': variant_dict['@type']
                            }
                        ]
                    }
                },
                {
                    'url': 'http://hl7.org/fhir/StructureDefinition/observation-geneticsAminoAcidChangeName',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://loinc.org',
                                'code': '48005-3',
                                'display': 'Exons {}'.format(variant_dict['@number-of-exons'])
                            }
                        ]
                    }
                },
                {
                    'url': 'http://lifeomic.com/fhir/StructureDefinition/observation-copyNumber',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://lifeomic.com',
                                'code': 'copyNumber',
                                'display': variant_dict['@copy-number']
                            }
                        ]
                    }
                }
            ],
            'id': observation_id
        }
        return observation
    return create


def create_observation(fasta, genes, project_id, subject_id, specimen_id, specimen_name, sequence_id):
    def create(variant_dict):
        observation_id = str(uuid.uuid4())
        position_value = variant_dict['@position']
        region, position = position_value.split(':')
        transcript = variant_dict['@transcript']
        cds_effect = variant_dict['@cds-effect'].replace('&gt;', '>')
        variant_name = '{}:c.{}'.format(transcript, cds_effect)
        chrom, offset, ref, alt = parse_hgvs(variant_name, fasta, genes)
        variantReadCount = int(round(int(variant_dict['@depth']) * float(variant_dict['@allele-fraction'])))

        observation = {
            'resourceType': 'Observation',
            'identifier': [{
                'system': 'https://lifeomic.com/observation/genetic',
                'value': '{}:{}:{}:{}'.format(chrom, offset, ref, alt)
            }],
            'meta': {
                'tag': [
                    {
                        'system': 'http://lifeomic.com/fhir/dataset',
                        'code': project_id
                    },
                    {
                        'system': 'http://lifeomic.com/fhir/source',
                        'code': 'LifeOmic Task Service'
                    }
                ]
            },
            'code': {
                'coding': [
                {
                    'system': 'http://loinc.org',
                    'code': '55233-1',
                    'display': 'Genetic analysis master panel-- This is the parent OBR for the panel holding all of the associated observations that can be reported with a molecular genetics analysis result.'
                }
                ]
            },
            'status': 'final',
            'subject': {
                'reference': 'Patient/{}'.format(subject_id)
            },
            'specimen': {
                'display': specimen_name,
                'reference': 'Specimen/{}'.format(specimen_id)
            },
            'valueCodeableConcept': {
                'coding': [
                    {
                    'system': 'http://foundationmedicine.com',
                    'code': variant_dict['@status'],
                    'display': 'Foundation - {}'.format(variant_dict['@status'].title())
                    }
                ]
            },
            'extension': [
                {
                    'url': 'http://hl7.org/fhir/StructureDefinition/observation-geneticsGene',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://www.genenames.org',
                                'code': '1100',
                                'display': variant_dict['@gene']
                            }
                        ]
                    }
                },
                {
                    'url': 'http://hl7.org/fhir/StructureDefinition/observation-geneticsDNASequenceVariantName',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://loinc.org',
                                'code': '48004-6',
                                'display': variant_name
                            }
                        ]
                    }
                },
                {
                    'url': 'http://hl7.org/fhir/StructureDefinition/observation-geneticsAminoAcidChangeType',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://snomed.info/sct',
                                'code': 'LL380-7',
                                'display': variant_dict['@functional-effect']
                            }
                        ]
                    }
                },
                {
                    'url': 'http://hl7.org/fhir/StructureDefinition/observation-geneticsAminoAcidChangeName',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://loinc.org',
                                'code': '48005-3',
                                'display': 'p.{}'.format(variant_dict['@protein-effect'])
                            }
                        ]
                    }
                },
                {
                    'url': 'http://hl7.org/fhir/StructureDefinition/observation-geneticsAllelicFrequency',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://loinc.org',
                                'code': '81258-6',
                                'display': variant_dict['@allele-fraction']
                            }
                        ]
                    }
                },
                {
                    'url': 'http://hl7.org/fhir/StructureDefinition/observation-geneticsGenomicSourceClass',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://loinc.org',
                                'code': '48002-0',
                                'display': 'somatic'
                            }
                        ]
                    }
                },
                {
                    'url': 'http://hl7.org/fhir/StructureDefinition/observation-geneticsSequence',
                    'valueReference': {
                        'reference': 'Sequence/{}'.format(sequence_id)
                    }
                },
                {
                    'url': 'http://lifeomic.com/fhir/StructureDefinition/observation-geneticsDNAPosition',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://loinc.org',
                                'code': '48001-2',
                                'display': position
                            }
                        ]
                    }
                },
                {
                    'url': 'http://lifeomic.com/fhir/StructureDefinition/observation-geneticsDNAChromosome',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://loinc.org',
                                'code': '47999-8',
                                'display': region
                            }
                        ]
                    }
                },
                {
                    'url': 'http://lifeomic.com/fhir/StructureDefinition/observation-geneticsTotalReadDepth',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://loinc.org',
                                'code': '82121-5',
                                'display': variant_dict['@depth']
                            }
                        ]
                    }
                },
                {
                    "url": "http://lifeomic.com/fhir/StructureDefinition/observation-geneticsVariantReadCount",
                    "valueCodeableConcept": {
                        "coding": [
                            {
                                "system": "http://loinc.org",
                                "code": "82121-5",
                                "display": str(variantReadCount)
                            }
                        ]
                    }
                },
                {
                    'url': 'http://lifeomic.com/fhir/StructureDefinition/observation-geneticsTranscriptID',
                    'valueCodeableConcept': {
                        'coding': [
                            {
                                'system': 'http://loinc.org',
                                'code': '51958-7',
                                'display': variant_dict['@transcript']
                            }
                        ]
                    }
                }
            ],
            'id': observation_id
        }
        return observation
    return create


def create_report(results_payload_dict, project_id, subject_id, specimen_id, specimen_name, file_url=None):
    report_id = str(uuid.uuid4())

    report = {
        'resourceType': 'DiagnosticReport',
        'meta': {
            'tag': [
                {
                    'system': 'http://lifeomic.com/fhir/dataset',
                    'code': project_id
                },
                {
                    'system': 'http://lifeomic.com/fhir/source',
                    'code': 'LifeOmic Task Service'
                }
            ]
        },
        'extension': [
            {
                'url': 'http://hl7.org/fhir/StructureDefinition/DiagnosticReport-geneticsAssessedCondition',
                'valueReference': {
                    'reference': results_payload_dict['FinalReport']['PMI']['SubmittedDiagnosis']
                }
            }
        ],
        'status': 'final',
        'code': {
            'text': results_payload_dict['FinalReport']['Sample']['TestType']
        },
        'issued': results_payload_dict['FinalReport']['PMI']['CollDate'],
        'subject': {
            'reference': 'Patient/{}'.format(subject_id)
        },
        'result': [],
        'id': report_id
    }

    if specimen_id is not None:
        report['specimen'] = [{
            'display': specimen_name,
            'reference': 'Specimen/{}'.format(specimen_id)
        }]

    if file_url is not None:
        report['presentedForm'] = [{
            'url': file_url,
            'contentType': 'application/pdf',
            'title': results_payload_dict['FinalReport']['Sample']['TestType']
        }]

    return report


def create_subject(results_payload_dict, project_id):
    subject_id = str(uuid.uuid4())
    pmi_dict = results_payload_dict['FinalReport']['PMI']

    subject = {
        'resourceType': 'Patient',
        'meta': {
            'tag': [
                {
                    'system': 'http://lifeomic.com/fhir/dataset',
                    'code': project_id
                },
                {
                    'system': 'http://lifeomic.com/fhir/source',
                    'code': 'LifeOmic Task Service'
                }
            ]
        },
        'name': [{
            'use': 'official',
            'family': pmi_dict['LastName'],
            'given': [pmi_dict['FirstName']]
        }],
        'identifier': [{
            'type': {
                'coding': [{
                    'system': 'http://hl7.org/fhir/v2/0203',
                    'code': 'MR'
                }]
            },
            'value': pmi_dict['MRN']
        }],
        'gender': pmi_dict['Gender'].lower(),
        'birthDate': pmi_dict['DOB'],
        'id': subject_id
    }
    return subject, subject_id


def create_sequence(project_id, subject_id, specimen_id, specimen_name):
    sequence_id = str(uuid.uuid4())

    sequence = {
        'resourceType': 'Sequence',
        'type': 'dna',
        'meta': {
            'tag': [
                {
                    'system': 'http://lifeomic.com/fhir/dataset',
                    'code': project_id
                },
                {
                    'system': 'http://lifeomic.com/fhir/source',
                    'code': 'LifeOmic Task Service'
                }
            ]
        },
        'patient': {
            'reference': 'Patient/{}'.format(subject_id)
        },
        'specimen': {
            'display': specimen_name,
            'reference': 'Specimen/{}'.format(specimen_id)
        },
        'referenceSeq': {
            'genomeBuild': 'GRCh37'
        },
        'id': sequence_id,
        'variant': []
    }
    return sequence, sequence_id


def create_specimen(results_payload_dict, project_id, subject_id):
    specimen_name = results_payload_dict['variant-report']['samples']['sample']['@name']
    specimen_id = str(uuid.uuid4())

    specimen = {
        'resourceType': 'Specimen',
        'meta': {
            'tag': [
                {
                    'system': 'http://lifeomic.com/fhir/dataset',
                    'code': project_id
                },
                {
                    'system': 'http://lifeomic.com/fhir/source',
                    'code': 'LifeOmic Task Service'
                }
            ]
        },
        'identifier': [
            {
                'value': specimen_name
            }
        ],
        'subject': {
            'reference': 'Patient/{}'.format(subject_id)
        },
        'id': specimen_id
    }
    return specimen, specimen_id, specimen_name


def write_vcf(results_payload_dict, fasta, genes, vcf_out_file):
    specimen_name = results_payload_dict['variant-report']['samples']['sample']['@name']

    with open('./unsorted.vcf', 'w+') as vcf_file:
        vcf_file.write('##fileformat=VCFv4.2\n')
        vcf_file.write('##fileDate={}\n'.format(datetime.date.today()))
        vcf_file.write('##source=foundation-xml-fhir\n')
        vcf_file.write('##reference=file://{}\n'.format(fasta))
        vcf_file.write('##INFO=<ID=DP,Number=1,Type=Integer,Description="Total Depth">\n')
        vcf_file.write('##INFO=<ID=AF,Number=A,Type=Float,Description="Allele Frequency">\n')
        vcf_file.write('##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">\n')
        vcf_file.write('##FORMAT=<ID=DP,Number=1,Type=Integer,Description="Read Depth">\n')
        vcf_file.write('##FORMAT=<ID=AD,Number=.,Type=Integer,Description="Number of reads harboring allele (in order specified by GT)">\n')
        vcf_file.write('##contig=<ID=chr1,length=248956422>\n')
        vcf_file.write('##contig=<ID=chr2,length=242193529>\n')
        vcf_file.write('##contig=<ID=chr3,length=198295559>\n')
        vcf_file.write('##contig=<ID=chr4,length=190214555>\n')
        vcf_file.write('##contig=<ID=chr5,length=181538259>\n')
        vcf_file.write('##contig=<ID=chr6,length=170805979>\n')
        vcf_file.write('##contig=<ID=chr7,length=159345973>\n')
        vcf_file.write('##contig=<ID=chr8,length=145138636>\n')
        vcf_file.write('##contig=<ID=chr9,length=138394717>\n')
        vcf_file.write('##contig=<ID=chr10,length=133797422>\n')
        vcf_file.write('##contig=<ID=chr11,length=135086622>\n')
        vcf_file.write('##contig=<ID=chr12,length=133275309>\n')
        vcf_file.write('##contig=<ID=chr13,length=114364328>\n')
        vcf_file.write('##contig=<ID=chr14,length=107043718>\n')
        vcf_file.write('##contig=<ID=chr15,length=101991189>\n')
        vcf_file.write('##contig=<ID=chr16,length=90338345>\n')
        vcf_file.write('##contig=<ID=chr17,length=83257441>\n')
        vcf_file.write('##contig=<ID=chr18,length=80373285>\n')
        vcf_file.write('##contig=<ID=chr19,length=58617616>\n')
        vcf_file.write('##contig=<ID=chr20,length=64444167>\n')
        vcf_file.write('##contig=<ID=chr21,length=46709983>\n')
        vcf_file.write('##contig=<ID=chr22,length=50818468>\n')
        vcf_file.write('##contig=<ID=chrX,length=156040895>\n')
        vcf_file.write('##contig=<ID=chrY,length=57227415>\n')
        vcf_file.write('##contig=<ID=chrM,length=16569>\n')
        vcf_file.write('#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t{}\n'.format(specimen_name))
        for variant_dict in results_payload_dict['variant-report']['short-variants']['short-variant']:
            cds_effect = variant_dict['@cds-effect'].replace('&gt;', '>')
            transcript = variant_dict['@transcript']
            dp = variant_dict['@depth']
            af = variant_dict['@allele-fraction']
            gt = '1/1' if float(variant_dict['@allele-fraction']) > 0.9 else '0/1'
            ad = int(round(int(dp) * float(af)))
            variant_name = '{}:c.{}'.format(transcript, cds_effect)
            chrom, offset, ref, alt = parse_hgvs(variant_name, fasta, genes)

            vcf_file.write('{}\t{}\t.\t{}\t{}\t.\t.\tDP={};AF={}\tGT:DP:AD\t{}:{}:{}\n'.format(chrom, offset, ref, alt, dp, af, gt, dp, ad))


def process(results_payload_dict, args):
    fhir_resources = []
    subject_id = args.subject_id

    if subject_id is None:
        subject, subject_id = create_subject(
            results_payload_dict, args.project_id)
        fhir_resources.append(subject)

    specimen_name = None
    specimen_id = None

    if (args.vcf_out_file is None):
        specimen, specimen_id, specimen_name = create_specimen(
            results_payload_dict, args.project_id, subject_id)
        sequence, sequence_id = create_sequence(
            args.project_id, subject_id, specimen_id, specimen_name)
        fhir_resources.append(specimen)
        fhir_resources.append(sequence)

    report = create_report(results_payload_dict, args.project_id,
                           subject_id, specimen_id, specimen_name, args.file_url)

    observations = []
    if ('short-variants' in results_payload_dict['variant-report'].keys() and
            'short-variant' in results_payload_dict['variant-report']['short-variants'].keys()):
        if (args.vcf_out_file is not None):
            write_vcf(results_payload_dict, args.fasta, args.genes, args.vcf_out_file)
        else:
            observations = list(map(create_observation(args.fasta, args.genes, args.project_id, subject_id, specimen_id, specimen_name, sequence_id),
                                results_payload_dict['variant-report']['short-variants']['short-variant']))

    if (args.vcf_out_file is None and
            'copy-number-alterations' in results_payload_dict['variant-report'].keys() and
            'copy-number-alteration' in results_payload_dict['variant-report']['copy-number-alterations'].keys()):
        observations.extend(list(map(create_copy_number_observation(args.project_id, subject_id, specimen_id, specimen_name, sequence_id),
                                results_payload_dict['variant-report']['copy-number-alterations']['copy-number-alteration'])))

    if (args.vcf_out_file is None):
        report['result'] = [
            {'reference': 'Observation/{}'.format(x['id'])} for x in observations]
        sequence['variant'] = [
            {'reference': 'Observation/{}'.format(x['id'])} for x in observations]

    fhir_resources.append(report)
    fhir_resources = fhir_resources + observations
    logger.info('Created %d FHIR resources', len(fhir_resources))

    return fhir_resources


def main():
    parser = argparse.ArgumentParser(
        prog='foundation-xml-fhir', description='Converts FoundationOne XML reports into FHIR resources.')
    parser.add_argument('-r, --reference', dest='fasta',
                        required=True, help='Path to reference genome')
    parser.add_argument('-g, --genes', dest='genes',
                        required=False, help='Path to genes file', default='/opt/app/refGene.hg19.txt')
    parser.add_argument('-x, --xml', dest='xml_file',
                        required=True, help='Path to the XML file')
    parser.add_argument('-p, --project', dest='project_id', required=True,
                        help='The ID of the project to link the resources to')
    parser.add_argument('-s, --subject', dest='subject_id', required=False,
                        help='The ID of the subject/patient to link the resources to')
    parser.add_argument('-o, --output', dest='out_file',
                        required=True, help='Path to write the FHIR JSON resources')
    parser.add_argument('-f, --file', dest='file_url',
                        required=False, help='The URL to the PDF Report in the PHC')
    parser.add_argument('-d, --pdf-output', dest='pdf_out_file',
                        required=False, help='Path to write the PDF file', default=None)
    parser.add_argument('-v, --vcf-output', dest='vcf_out_file',
                        required=False, help='Path to write the VCF file', default=None)

    args = parser.parse_args()
    logger.info('Converting XML to FHIR with args: %s',
                json.dumps(args.__dict__))

    # pyfaidx has a bug with bgzipped files.  Unzip the genome for now
    # https://github.com/mdshw5/pyfaidx/issues/125
    if (args.fasta.lower().endswith('.bgz') or
            args.fasta.lower().endswith('.gz')):
        args.fasta = unzip(args.fasta)

    xml_dict = read_xml(args.xml_file)
    fhir_resources = process(
        xml_dict['rr:ResultsReport']['rr:ResultsPayload'], args)
    save_json(fhir_resources, args.out_file)
    logger.info('Saved FHIR resources to %s', args.out_file)

    if args.pdf_out_file is not None and 'ReportPDF' in xml_dict['rr:ResultsReport']['rr:ResultsPayload']:
        pdf = base64.b64decode(xml_dict['rr:ResultsReport']['rr:ResultsPayload']['ReportPDF'])
        with open(args.pdf_out_file, "w") as pdf_file:
            pdf_file.write(pdf)
        logger.info('Saved PDF report to %s', args.pdf_out_file)

    if args.vcf_out_file is not None:
        call(['vt', 'sort', '-o', args.vcf_out_file, './unsorted.vcf'])


if __name__ == '__main__':
    main()
