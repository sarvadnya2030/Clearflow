package com.clearflow.gateway;

import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.lang.syntax.ArchRuleDefinition;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.stereotype.Repository;
import org.springframework.web.bind.annotation.RestController;

/**
 * ArchUnit architectural rule enforcement for the gateway module.
 *
 * <p>Rules enforce the layering contract and prevent architectural drift.
 * Violations fail the CI pipeline — catching issues at commit-time,
 * not in production.
 */
class PaymentArchTest {

    private final JavaClasses classes = new ClassFileImporter()
            .importPackages("com.clearflow.gateway");

    @Test
    @DisplayName("@RestControllers must reside in the controller package")
    void restControllersInControllerPackage() {
        ArchRuleDefinition.classes()
                .that().areAnnotatedWith(RestController.class)
                .should().resideInAnyPackage("..controller..")
                .check(classes);
    }

    @Test
    @DisplayName("Service layer must not use KafkaTemplate directly")
    void serviceLayerNoKafkaTemplate() {
        ArchRuleDefinition.noClasses()
                .that().resideInAnyPackage("..service..")
                .should().dependOnClassesThat().haveSimpleName("KafkaTemplate")
                .check(classes);
    }

    @Test
    @DisplayName("Service layer must not use JmsTemplate directly")
    void serviceLayerNoJmsTemplate() {
        ArchRuleDefinition.noClasses()
                .that().resideInAnyPackage("..service..")
                .should().dependOnClassesThat().haveSimpleName("JmsTemplate")
                .check(classes);
    }

    @Test
    @DisplayName("Domain objects must not depend on Spring framework annotations")
    void domainIsSpringFree() {
        ArchRuleDefinition.noClasses()
                .that().resideInAnyPackage("..domain..")
                .should().dependOnClassesThat().resideInAnyPackage(
                        "org.springframework.stereotype..",
                        "org.springframework.web.bind.annotation..",
                        "org.springframework.data..")
                .check(classes);
    }

    @Test
    @DisplayName("No @Repository annotation in gateway (JdbcTemplate used directly in messaging layer)")
    void noRepositoryAnnotations() {
        ArchRuleDefinition.noClasses()
                .should().beAnnotatedWith(Repository.class)
                .check(classes);
    }

    @Test
    @DisplayName("Messaging classes must not depend on service layer (unidirectional flow)")
    void messagingDoesNotDependOnService() {
        ArchRuleDefinition.noClasses()
                .that().resideInAnyPackage("..messaging..")
                .should().dependOnClassesThat().resideInAnyPackage("..service..")
                .check(classes);
    }
}
