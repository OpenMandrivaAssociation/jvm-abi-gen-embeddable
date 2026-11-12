Name:		jvm-abi-gen-embeddable
Version:	2.4.21
Release:	1
Summary:	Kotlin/JVM ABI generator compiler plugin
Group:		Development/Java
License:	Apache-2.0
URL:		https://github.com/JetBrains/kotlin
# Kotlin tag v2.4.21, plugins/jvm-abi-gen, artifact jvm-abi-gen-embeddable.
# kotlinc 2.0.21 rejects explicit backing fields and bracket destructures.
# Patch0 lowers those. SMAPBuilder.build gained a validate parameter, and
# CompileEnvironmentUtil.writeToJar now takes CompilerConfiguration. Both are
# compiled from this tree as a classpath overlay and are not installed.
# kotlin.metadata classes are copied from the installed kotlin-metadata-jvm
# jar so a kotlinc plugin classloader can strip private declarations.
Source0:	jvm-abi-gen-embeddable-%{version}.tar.gz
Patch0:		jvm-abi-gen-embeddable-kotlinc20.patch

BuildArch:	noarch
BuildRequires:	java-21-openjdk-devel
BuildRequires:	kotlin = 2.0.21
BuildRequires:	kotlin-stdlib >= 2.4.21-2
BuildRequires:	mvn(org.jetbrains.kotlin:kotlin-metadata-jvm) = 2.4.21
BuildRequires:	sysjar
BuildRequires:	javapackages-filesystem

%description
org.jetbrains.kotlin:jvm-abi-gen-embeddable %{version}.
The Kotlin/JVM ABI compiler plugin from tag v2.4.21, compiled with the
installed kotlinc 2.0.21. Metadata classes from kotlin-metadata-jvm are
packed inside the plugin jar.

%prep
%autosetup -n jvm-abi-gen-embeddable-%{version} -p1
find . -type f \( -name '*.jar' -o -name '*.class' -o -name '*.so' -o -name '*.node' -o -name '*.wasm' \) -print > binaries.list
if [ -s binaries.list ]; then
	cat binaries.list
	exit 1
fi

%build
set -eo pipefail
export JAVA_HOME=%{_jvmdir}/java-21-openjdk
export PATH="$JAVA_HOME/bin:/usr/bin:/bin"
STDLIB=%{_javadir}/kotlin-stdlib-%{version}.jar
META=%{_javadir}/kotlin-metadata-jvm.jar
COMPILER=/usr/share/kotlin/lib/kotlin-compiler.jar
test -s "$STDLIB"
test -s "$META"
test -s "$COMPILER"
/bin/rm -rf api-classes smap-classes writeto-classes plugin-classes stage meta-extract
mkdir -p api-classes smap-classes writeto-classes plugin-classes
find compiler/plugin-api/src compiler/util/src -name '*.kt' | sort > api.list
kotlinc -J-Xmx2g -jvm-target 1.8 -language-version 2.0 -Xwhen-guards -Xjvm-default=all -no-stdlib -jdk-home "$JAVA_HOME" \
	-opt-in=org.jetbrains.kotlin.compiler.plugin.ExperimentalCompilerApi \
	-module-name kotlin-plugin-api-overlay \
	-cp "$STDLIB:$COMPILER" \
	-d api-classes @api.list < /dev/null
find compiler/backend.common.jvm/src compiler/backend/src -name '*.kt' | sort > smap.list
kotlinc -J-Xmx2g -jvm-target 1.8 -language-version 2.0 -Xwhen-guards -Xjvm-default=all -no-stdlib -jdk-home "$JAVA_HOME" \
	-module-name kotlin-smap-overlay \
	-cp "$STDLIB:$COMPILER" \
	-d smap-classes @smap.list < /dev/null
javac --release 8 -proc:none -cp "$COMPILER" -d writeto-classes \
	overlay/org/jetbrains/kotlin/cli/jvm/compiler/CompileEnvironmentUtil.java
find plugins/jvm-abi-gen/src -name '*.kt' | sort > plugin.list
kotlinc -J-Xmx2g -jvm-target 1.8 -language-version 2.0 -Xwhen-guards -Xjvm-default=all -no-stdlib -jdk-home "$JAVA_HOME" \
	-opt-in=org.jetbrains.kotlin.compiler.plugin.ExperimentalCompilerApi \
	-module-name jvm-abi-gen \
	-cp "$STDLIB:$META:api-classes:smap-classes:writeto-classes:$COMPILER" \
	-d plugin-classes @plugin.list < /dev/null
test "$(find plugin-classes -name '*.class' | wc -l)" -gt 0
find plugin-classes -name '*.class' | sed 's|^plugin-classes/||;s|\.class$||;s|/|.|g' > class.list
smap_hit=0
write_hit=0
while IFS= read -r class; do
	javap -c -p -classpath plugin-classes "$class" > one.javap
	if grep -F -q 'SMAPBuilder.build:(Ljava/util/List;ZZ)Ljava/lang/String;' one.javap; then
		smap_hit=1
	fi
	if grep -F -q 'writeToJar:(Ljava/io/File;ZZZLorg/jetbrains/kotlin/name/FqName;Lorg/jetbrains/kotlin/backend/common/output/OutputFileCollection;Lorg/jetbrains/kotlin/config/CompilerConfiguration;)V' one.javap; then
		write_hit=1
	fi
done < class.list
test "$smap_hit" = 1
test "$write_hit" = 1
mkdir -p stage/META-INF/services meta-extract
/bin/cp -a plugin-classes/. stage/
/bin/cp -a plugins/jvm-abi-gen/resources/META-INF/services/. stage/META-INF/services/
(
	cd meta-extract
	jar xf "$META" kotlin/metadata META-INF/services/kotlin.metadata.internal.extensions.MetadataExtensions
)
/bin/cp -a meta-extract/kotlin stage/
/bin/cp -f meta-extract/META-INF/services/kotlin.metadata.internal.extensions.MetadataExtensions stage/META-INF/services/
cat > manifest.mf << 'EOF'
Manifest-Version: 1.0
Automatic-Module-Name: kotlin.jvm.abi.gen
Created-By: OpenMandriva

EOF
jar cfm jvm-abi-gen-embeddable.jar manifest.mf -C stage .
jar tf jvm-abi-gen-embeddable.jar > jar.list
cat > forbidden.list << 'EOF'
org/jetbrains/kotlin/compiler/plugin/CompilerPluginRegistrar.class
org/jetbrains/kotlin/codegen/inline/SMAPBuilder.class
org/jetbrains/kotlin/cli/jvm/compiler/CompileEnvironmentUtil.class
org/jetbrains/kotlin/extensions/ExtensionPointDescriptor.class
org/jetbrains/kotlin/extensions/ProjectExtensionDescriptor.class
kotlin/ExperimentalContextParameters.class
EOF
while IFS= read -r bad; do
	if grep -F -qx "$bad" jar.list; then
		echo "forbidden $bad"
		exit 1
	fi
done < forbidden.list
cat > required.list << 'EOF'
META-INF/services/org.jetbrains.kotlin.compiler.plugin.CompilerPluginRegistrar
META-INF/services/org.jetbrains.kotlin.compiler.plugin.CommandLineProcessor
META-INF/services/kotlin.metadata.internal.extensions.MetadataExtensions
kotlin/metadata/KmClass.class
org/jetbrains/kotlin/jvm/abi/JvmAbiCommandLineProcessor.class
org/jetbrains/kotlin/jvm/abi/JvmAbiComponentRegistrar.class
EOF
while IFS= read -r need; do
	grep -F -qx "$need" jar.list
done < required.list
desc=$(jar --describe-module --file jvm-abi-gen-embeddable.jar)
printf '%s\n' "$desc" | grep -F -qx 'kotlin.jvm.abi.gen automatic'
if printf '%s\n' "$desc" | grep -F -q 'Unable'; then
	echo "describe failed"
	exit 1
fi
cat > jvm-abi-gen-embeddable.pom << END
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>org.jetbrains.kotlin</groupId>
  <artifactId>jvm-abi-gen-embeddable</artifactId>
  <version>%{version}</version>
  <name>jvm-abi-gen-embeddable</name>
  <description>Kotlin/JVM ABI generator compiler plugin</description>
  <url>https://github.com/JetBrains/kotlin</url>
  <licenses>
    <license>
      <name>Apache-2.0</name>
      <url>https://www.apache.org/licenses/LICENSE-2.0.txt</url>
    </license>
  </licenses>
  <dependencies>
    <dependency>
      <groupId>org.jetbrains.kotlin</groupId>
      <artifactId>kotlin-stdlib</artifactId>
      <version>%{version}</version>
    </dependency>
    <dependency>
      <groupId>org.jetbrains.kotlin</groupId>
      <artifactId>kotlin-metadata-jvm</artifactId>
      <version>%{version}</version>
    </dependency>
  </dependencies>
</project>
END

%install
set -eo pipefail
sysjar install --buildroot %{buildroot} \
	--artifact jvm-abi-gen-embeddable.pom:jvm-abi-gen-embeddable.jar \
	--file-name jvm-abi-gen-embeddable \
	--filelist .mfiles
idx="%{buildroot}/usr/share/sysjar/index/org.jetbrains.kotlin/jvm-abi-gen-embeddable.sysjar"
test -s "$idx"
grep -F -q '"version": "%{version}"' "$idx"
grep -F -q '"artifactId": "jvm-abi-gen-embeddable"' "$idx"
test -s %{buildroot}%{_javadir}/jvm-abi-gen-embeddable.jar

%check
set -eo pipefail
export JAVA_HOME=%{_jvmdir}/java-21-openjdk
export PATH="$JAVA_HOME/bin:/usr/bin:/bin"
JAR=%{buildroot}%{_javadir}/jvm-abi-gen-embeddable.jar
STDLIB=%{_javadir}/kotlin-stdlib-%{version}.jar
META=%{_javadir}/kotlin-metadata-jvm.jar
COMPILER=/usr/share/kotlin/lib/kotlin-compiler.jar
test -s "$JAR"
test -s "$STDLIB"
mkdir -p check/out
cat > check/Probe.kt << 'EOF'
import org.jetbrains.kotlin.compiler.plugin.AbstractCliOption
import org.jetbrains.kotlin.config.CompilerConfiguration
import org.jetbrains.kotlin.jvm.abi.JvmAbiCommandLineProcessor
import org.jetbrains.kotlin.jvm.abi.JvmAbiComponentRegistrar
import org.jetbrains.kotlin.jvm.abi.JvmAbiConfigurationKeys

fun main() {
    val processor = JvmAbiCommandLineProcessor()
    if (processor.pluginId != "org.jetbrains.kotlin.jvm.abi") error("id " + processor.pluginId)
    val names = processor.pluginOptions.map { it.optionName }
    if (names != listOf(
            "outputDir",
            "removeDebugInfo",
            "removeDataClassCopyIfConstructorIsPrivate",
            "preserveDeclarationOrder",
            "removePrivateClasses",
            "treatInternalAsPrivate",
        )
    ) error("options " + names)
    val cfg = CompilerConfiguration()
    processor.processOption(JvmAbiCommandLineProcessor.OUTPUT_PATH_OPTION as AbstractCliOption, "abi.jar", cfg)
    processor.processOption(JvmAbiCommandLineProcessor.REMOVE_DEBUG_INFO_OPTION as AbstractCliOption, "true", cfg)
    processor.processOption(JvmAbiCommandLineProcessor.REMOVE_PRIVATE_CLASSES_OPTION as AbstractCliOption, "false", cfg)
    val path = cfg.get(JvmAbiConfigurationKeys.JVM_ABI_OUTPUT_PATH)
    val debug = cfg.get(JvmAbiConfigurationKeys.JVM_ABI_REMOVE_DEBUG_INFO)
    val priv = cfg.get(JvmAbiConfigurationKeys.JVM_ABI_REMOVE_PRIVATE_CLASSES)
    if (path != "abi.jar" || debug != true || priv != false) error("cfg " + path + " " + debug + " " + priv)
    val registrar = JvmAbiComponentRegistrar()
    if (registrar.pluginId != "org.jetbrains.kotlin.jvm.abi") error("registrar " + registrar.pluginId)
    if (!registrar.supportsK2) error("supportsK2")
    val code = JvmAbiCommandLineProcessor::class.java.protectionDomain.codeSource.location.path
    if (!code.endsWith("jvm-abi-gen-embeddable.jar")) error("code " + code)
    val meta = kotlin.metadata.KmClass::class.java.protectionDomain.codeSource.location.path
    if (!meta.endsWith("jvm-abi-gen-embeddable.jar")) error("meta " + meta)
    println("jvm_abi_gen_ok " + path + " " + debug + " " + names.size + " " + registrar.pluginId)
}
EOF
kotlinc -J-Xmx1g -jvm-target 1.8 -language-version 2.0 -no-stdlib -jdk-home "$JAVA_HOME" \
	-opt-in=org.jetbrains.kotlin.compiler.plugin.ExperimentalCompilerApi \
	-cp "$JAR:$STDLIB:$META:$COMPILER" -d check/out check/Probe.kt < /dev/null
java -cp "check/out:$JAR:$STDLIB:$META:$COMPILER" ProbeKt > check/out.txt
cat check/out.txt
grep -F -qx 'jvm_abi_gen_ok abi.jar true 6 org.jetbrains.kotlin.jvm.abi' check/out.txt

%files -f .mfiles
%license license/LICENSE.txt
%doc license/NOTICE.txt
